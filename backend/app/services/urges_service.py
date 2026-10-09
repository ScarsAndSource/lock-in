"""
Urges. Quick-capture = just an outcome (resisted/relapsed); that IS a complete log, never a draft.
Detail (intensity, trigger, coping, note) can be added later. All free text is encrypted at rest
and is NEVER read by the retro/insight layers: they only ever see counts from summary().

relapse_free_days_pct is the rolling share of days WITHOUT a logged relapse -- it dents, it never
resets to zero. It is None when nothing was logged in the window (no data != 100%).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.dates import Clock, utc_now
from app.domain import UrgeLog, UrgeOutcome
from app.exceptions import DataIntegrityError, NotFoundError, ValidationError
from app.repositories.urge_repository import UrgeRepository
from app.security import FieldEncryptor
from app.services.profile_service import ProfileService

_MAX_RANGE_DAYS = 90
_MAX_BACKFILL_DAYS = 400
_FUTURE_SLACK = timedelta(minutes=5)
_DETAIL_KEYS = frozenset({"intensity", "trigger_context", "coping_strategy", "note"})


@dataclass(slots=True)
class UrgeSummary:
    total: int = 0
    resisted: int = 0
    relapsed: int = 0
    resist_rate_pct: float | None = None
    relapse_free_days_pct: float | None = None


@dataclass(slots=True)
class UrgeView:
    log: UrgeLog
    trigger_context: str | None = None
    coping_strategy: str | None = None
    note: str | None = None


def _local_date(when: datetime, tz_name: str) -> date:
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        tz = ZoneInfo("UTC")
    return when.astimezone(tz).date()


def _summarize(rows: list[UrgeLog], window_days: int) -> UrgeSummary:
    resisted = sum(1 for r in rows if r.outcome == UrgeOutcome.RESISTED)
    relapse_days = {r.log_date for r in rows if r.outcome == UrgeOutcome.RELAPSED}
    return UrgeSummary(
        total=len(rows), resisted=resisted, relapsed=len(rows) - resisted,
        resist_rate_pct=round(100.0 * resisted / len(rows), 1) if rows else None,
        relapse_free_days_pct=round(100.0 * (window_days - len(relapse_days)) / window_days, 1) if rows else None,
    )


class UrgesService:
    def __init__(
        self, repo: UrgeRepository | None = None, encryptor: FieldEncryptor | None = None,
        profiles: ProfileService | None = None, clock: Clock = utc_now,
    ):
        self._repo = repo
        self._enc = encryptor
        self._profiles = profiles
        self._clock = clock

    def _need(self) -> None:
        if self._repo is None or self._enc is None or self._profiles is None:
            raise RuntimeError("UrgesService is not wired to its dependencies.")

    def _encrypt(self, text: str | None) -> bytes | None:
        return self._enc.encrypt(text) if text else None

    def _view(self, log: UrgeLog, details: bool) -> UrgeView:
        if not details:
            return UrgeView(log)
        try:
            return UrgeView(
                log, self._enc.decrypt(log.trigger_context_encrypted),
                self._enc.decrypt(log.coping_strategy_encrypted), self._enc.decrypt(log.note_encrypted),
            )
        except ValueError as exc:
            raise DataIntegrityError(str(exc)) from exc

    # ---------------------------------------------------------------- write
    async def capture(
        self, user_id: UUID, outcome: UrgeOutcome, occurred_at: datetime | None = None,
        intensity: int | None = None, trigger_context: str | None = None,
        coping_strategy: str | None = None, note: str | None = None,
    ) -> UrgeView:
        self._need()
        now = self._clock()
        when = occurred_at or now
        if when.tzinfo is None:
            raise ValidationError("occurred_at needs a timezone (e.g. 2026-12-31T23:10:00+05:30).")
        if when > now + _FUTURE_SLACK:
            raise ValidationError("Can't log an urge in the future.")
        if now - when > timedelta(days=_MAX_BACKFILL_DAYS):
            raise ValidationError(f"Can't backfill more than {_MAX_BACKFILL_DAYS} days.")
        if intensity is not None and not 1 <= intensity <= 10:
            raise ValidationError("intensity must be between 1 and 10.")
        tz_name = (await self._profiles.get(user_id)).timezone
        log = await self._repo.add(UrgeLog(
            id=uuid4(), user_id=user_id, occurred_at=when, log_date=_local_date(when, tz_name),
            outcome=outcome, intensity=intensity,
            trigger_context_encrypted=self._encrypt(trigger_context),
            coping_strategy_encrypted=self._encrypt(coping_strategy), note_encrypted=self._encrypt(note),
        ))
        return self._view(log, details=True)

    async def add_detail(self, user_id: UUID, urge_id: UUID, changes: dict) -> UrgeView:
        """Only keys present in `changes` are touched. null or "" clears a field."""
        self._need()
        if not changes:
            raise ValidationError("Nothing to update.")
        unknown = set(changes) - _DETAIL_KEYS
        if unknown:
            raise ValidationError(f"Unknown fields: {sorted(unknown)}")
        columns: dict = {}
        for key, value in changes.items():
            if key == "intensity":
                if value is not None and not 1 <= value <= 10:
                    raise ValidationError("intensity must be between 1 and 10.")
                columns["intensity"] = value
            else:
                columns[f"{key}_encrypted"] = self._encrypt(value)
        updated = await self._repo.update_detail(user_id, urge_id, columns)
        if updated is None:
            raise NotFoundError("No urge log found for this user.")
        return self._view(updated, details=True)

    async def delete(self, user_id: UUID, urge_id: UUID) -> None:
        self._need()
        if not await self._repo.delete(user_id, urge_id):
            raise NotFoundError("No urge log found for this user.")

    # ---------------------------------------------------------------- read
    async def list_views(self, user_id: UUID, start: date, end: date, details: bool) -> list[UrgeView]:
        self._need()
        if end < start:
            raise ValidationError("end_date must not be before start_date.")
        if (end - start).days > _MAX_RANGE_DAYS:
            raise ValidationError(f"Range too large -- max {_MAX_RANGE_DAYS} days per request.")
        return [self._view(l, details) for l in await self._repo.list_in_range(user_id, start, end)]

    async def summary(
        self, user_id: UUID, end_date: date | None, window_days: int
    ) -> tuple[date, UrgeSummary, float | None]:
        """(end, this window, PREVIOUS window's resist rate) -- the shape RetroService expects."""
        if self._repo is None:
            return end_date or date.today(), UrgeSummary(), None
        end = end_date or await self._profiles.today(user_id)
        start = end - timedelta(days=window_days - 1)
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=window_days - 1)
        now_rows = await self._repo.list_in_range(user_id, start, end)
        prev_rows = await self._repo.list_in_range(user_id, prev_start, prev_end)
        return end, _summarize(now_rows, window_days), _summarize(prev_rows, window_days).resist_rate_pct

    async def relapse_free_stats(self, user_id: UUID, end_date: date, window_days: int) -> tuple[float, int]:
        """(% of days with no logged relapse, longest relapse-free run in the window -- reference only)."""
        self._need()
        start = end_date - timedelta(days=window_days - 1)
        relapse_days = {
            r.log_date for r in await self._repo.list_in_range(user_id, start, end_date)
            if r.outcome == UrgeOutcome.RELAPSED
        }
        longest = run = 0
        for i in range(window_days):
            if start + timedelta(days=i) in relapse_days:
                run = 0
            else:
                run += 1
                longest = max(longest, run)
        return round(100.0 * (window_days - len(relapse_days)) / window_days, 1), longest
