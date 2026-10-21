"""
Passive capture: let the phone's own automations log sleep and screen time with zero taps.

A PWA cannot read the OS's sleep or screen-time data, but the OS can call a URL: an iOS Shortcuts personal automation
("Sleep Focus turns on / off", "alarm is stopped") or Android Tasker / MacroDroid. Each automation carries ONE ingest
token. Properties, all enforced here:

  write-only   a token can add events (sleep_start, sleep_end, screen_time) and nothing else: it cannot read a single
               row back, list anything, or touch habits, tasks, journal or settings.
  per-device   one token per automation, labelled; revoke one without touching the others.
  revocable    the token is an HMAC-signed handle to a row; every call checks the row and revoked_at, so revoking works
               instantly. The token string is never stored, so a database leak yields no usable credentials.
  bounded      an event must be timestamped within the last 36 hours and not in the future; minutes 0..1440; at most
               MAX_ACTIVE_TOKENS live tokens per person; rate limited per token.

Every write goes through SleepService / ScreenTimeService, so dates, ranges and validation are the app's own.
A sleep value from an automation overwrites the previous value of the SAME field (latest wins) but never touches the
other fields (quality, the other end of the night), and an auto-filled default is never mistaken for evidence.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from app.dates import Clock, utc_now
from app.domain import IngestToken, ScreenTimeSource
from app.exceptions import NotFoundError, ValidationError
from app.repositories.ingest_repository import IngestTokenRepository
from app.repositories.sleep_repository import SleepRepository
from app.services.profile_service import ProfileService
from app.services.screen_time_service import ScreenTimeService
from app.services.sleep_service import SleepService
from app.services.task_time import zone

TOKEN_PREFIX = "lk1_"
MAX_ACTIVE_TOKENS = 8
MAX_EVENT_AGE = timedelta(hours=36)
FUTURE_SLACK = timedelta(minutes=5)
BEDTIME_NEXT_DAY_FROM_HOUR = 15      # a bedtime after 15:00 belongs to the night that ends TOMORROW morning
KINDS = ("sleep_start", "sleep_end", "screen_time")
_PURPOSE = b"lockin/ingest/v1"


class IngestAuthError(Exception):
    """Bad, tampered, unknown or revoked token. One message for all of them: no probing."""


def purpose_secret(base: bytes) -> bytes:
    return hmac.new(base, _PURPOSE, hashlib.sha256).digest()


def _sig(secret: bytes, body: str) -> str:
    return base64.urlsafe_b64encode(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()).rstrip(b"=").decode()


def mint_token(secret: bytes, user_id: UUID, token_id: UUID) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"u": str(user_id), "t": str(token_id)}, separators=(",", ":")).encode()).rstrip(b"=").decode()
    return f"{TOKEN_PREFIX}{body}.{_sig(secret, body)}"


def verify_token(secret: bytes, token: str) -> tuple[UUID, UUID]:
    if not isinstance(token, str) or not token.startswith(TOKEN_PREFIX) or len(token) > 400 or token.count(".") != 1:
        raise IngestAuthError()
    body, sig = token[len(TOKEN_PREFIX):].split(".")
    try:
        body.encode("ascii")
        sig.encode("ascii")
    except UnicodeEncodeError as exc:
        raise IngestAuthError() from exc
    if not hmac.compare_digest(_sig(secret, body), sig):
        raise IngestAuthError()
    try:
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return UUID(data["u"]), UUID(data["t"])
    except (ValueError, KeyError, TypeError) as exc:
        raise IngestAuthError() from exc


@dataclass(slots=True)
class IngestResult:
    kind: str
    day: date
    message: str


class IngestService:
    def __init__(
        self, tokens: IngestTokenRepository, sleep: SleepService, sleep_repo: SleepRepository,
        screen: ScreenTimeService, profiles: ProfileService, secret: bytes, clock: Clock = utc_now,
    ):
        self._tokens, self._sleep, self._sleep_repo, self._screen = tokens, sleep, sleep_repo, screen
        self._profiles, self._secret, self._clock = profiles, purpose_secret(secret), clock

    # ------------------------------------------------------------------ token management (signed-in)
    async def create_token(self, user_id: UUID, label: str) -> tuple[IngestToken, str]:
        clean = " ".join(label.split())[:40]
        if not clean:
            raise ValidationError("Give the automation a short name, like 'iPhone sleep'.")
        live = [t for t in await self._tokens.list(user_id) if t.revoked_at is None]
        if len(live) >= MAX_ACTIVE_TOKENS:
            raise ValidationError(f"You already have {MAX_ACTIVE_TOKENS} active automations. Revoke one first.")
        token = await self._tokens.create(IngestToken(id=uuid4(), user_id=user_id, label=clean, created_at=self._clock()))
        return token, mint_token(self._secret, user_id, token.id)   # shown ONCE; never stored

    async def list_tokens(self, user_id: UUID) -> list[IngestToken]:
        return await self._tokens.list(user_id)

    async def revoke(self, user_id: UUID, token_id: UUID) -> None:
        if not await self._tokens.revoke(user_id, token_id, self._clock()):
            raise NotFoundError("No active automation with that id.")

    # ------------------------------------------------------------------ token holder (no session)
    def identify(self, token: str) -> tuple[UUID, UUID]:
        return verify_token(self._secret, token)

    async def handle_event(
        self, user_id: UUID, token_id: UUID, kind: str, at: datetime | None, minutes: int | None, day: date | None,
    ) -> IngestResult:
        now = self._clock()
        row = await self._tokens.get(user_id, token_id)
        if row is None or row.revoked_at is not None:
            raise IngestAuthError()
        if kind not in KINDS:
            raise ValidationError(f"kind must be one of {', '.join(KINDS)}.")
        when = at or now
        if when.tzinfo is None:
            raise ValidationError("at must include a timezone offset.")
        if when > now + FUTURE_SLACK or now - when > MAX_EVENT_AGE:
            raise ValidationError("That event is too old or in the future.")
        await self._tokens.touch(user_id, token_id, now)

        tz = zone((await self._profiles.get(user_id)).timezone)
        local = when.astimezone(tz)

        if kind == "screen_time":
            if minutes is None or not 0 <= minutes <= 1440:
                raise ValidationError("minutes must be 0-1440.")
            d = day or local.date()
            await self._screen.log_screen_time(user_id, d, minutes, ScreenTimeSource.AUTOMATION, None)
            return IngestResult(kind, d, f"Screen time {minutes} min logged.")

        if kind == "sleep_start":
            d = local.date() + timedelta(days=1 if local.hour >= BEDTIME_NEXT_DAY_FROM_HOUR else 0)
            await self._merge_sleep(user_id, d, bed=local.time().replace(second=0, microsecond=0))
            return IngestResult(kind, d, f"Bedtime {local:%H:%M} noted.")

        d = local.date()
        await self._merge_sleep(user_id, d, woke=local.time().replace(second=0, microsecond=0))
        return IngestResult(kind, d, f"Wake time {local:%H:%M} noted.")

    async def _merge_sleep(self, user_id: UUID, d: date, *, bed=None, woke=None) -> None:
        existing = await self._sleep_repo.get_log(user_id, d)
        keep = existing if existing is not None and not existing.is_default else None   # a guess is not evidence
        await self._sleep.log_sleep(
            user_id, d,
            bed if bed is not None else (keep.time_to_bed if keep else None),
            woke if woke is not None else (keep.time_woke if keep else None),
            keep.self_rated_quality if keep else None,
        )
