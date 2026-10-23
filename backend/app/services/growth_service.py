"""
Growth layer: mini journal, identity ("who you want to become"), habit check-ups (autopsy), notes to future self.

Principles
  * Deterministic. No LLM call anywhere in here, so it costs no tokens and can't hallucinate a diagnosis.
  * Private. Everything the person writes is encrypted with the same FieldEncryptor as check-in notes and urges.
  * Quiet. A check-up opens at most once per habit per cooldown; "later" and "skip" are always available.
  * The journal is the check-in journal: one field per day, so there is never a second place a note could hide.
Methods return plain dicts whose keys match schemas_growth.py.
"""
from __future__ import annotations

import base64
import binascii
from datetime import date, time, timedelta
from typing import Any
from uuid import UUID

from app.dates import Clock, utc_now
from app.domain import TargetFrequency
from app.exceptions import ConflictError, DataIntegrityError, NotFoundError, ValidationError
from app.services.goals_service import clean_text

STICKERS = ("🌱", "☕", "🌙", "✨", "🍀", "🧸", "🌧️", "🔥")
JOURNAL_MAX = 10_000                 # same ceiling as the check-in note
IDENTITY_MIN_CHECKINS = 5            # don't ask for a "why" before they've shown up a few times

AUTOPSY_WINDOW_DAYS = 21
AUTOPSY_MIN_EXPECTED = 6.0           # at least this many scheduled days in the window, else too little evidence
AUTOPSY_FAIL_BELOW_PCT = 30.0
AUTOPSY_LATER_DAYS = 7
AUTOPSY_SKIP_DAYS = 30
AUTOPSY_DONE_DAYS = 30
REASONS = ("too_big", "wrong_time", "wrong_trigger", "dont_care")

FUTURE_MAX_ACTIVE = 5
FUTURE_TEXT_MAX = 280
FUTURE_AUDIO_MAX_BYTES = 400_000
FUTURE_AUDIO_MAX_SECONDS = 25
DEFAULT_SLIP_MINUTE = 23 * 60
_AUDIO_MIMES = frozenset({"audio/webm", "audio/mp4", "audio/ogg", "audio/mpeg", "audio/wav", "audio/x-m4a", "audio/aac"})
_DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _label(freq: TargetFrequency) -> str:
    if freq.type == "n_per_week":
        return f"{freq.count}× a week"
    days = sorted(freq.days)
    return "every day" if len(days) == 7 else ", ".join(_DAY_NAMES[d] for d in days)


def _lighter(freq: TargetFrequency) -> TargetFrequency | None:
    """Roughly half the load, never below once a week. None when there is nothing lighter to offer."""
    if freq.type == "n_per_week":
        count = freq.count or 1
        if count <= 1:
            return None
        return TargetFrequency(type="n_per_week", count=max(1, (count + 1) // 2))
    days = tuple(sorted(freq.days))
    if len(days) <= 1:
        return None
    return TargetFrequency(type="weekdays", days=days[::2])


def _hhmm(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t is not None else None


def _parse_hhmm(raw: str | None) -> time | None:
    if raw is None or not raw.strip():
        return None
    try:
        hh, mm = raw.strip().split(":")[:2]
        return time(int(hh), int(mm))
    except (ValueError, IndexError) as exc:
        raise ValidationError("Time must look like 23:00.") from exc


def slip_minute(send_at: time | None, windows: list[Any]) -> int:
    """Minute-of-day a note should arrive: the time the person chose, else the start of their strongest LIVE urge
    window (risk_windows.RiskWindow), else 23:00."""
    if send_at is not None:
        return send_at.hour * 60 + send_at.minute
    live = [w for w in windows if w.recent_events > 0]
    return live[0].start_hour * 60 if live else DEFAULT_SLIP_MINUTE


class GrowthService:
    def __init__(
        self, repo, encryptor, profiles, stats, habit_repo, habits, intentions, clock: Clock = utc_now,
    ):
        self._repo, self._encryptor, self._profiles = repo, encryptor, profiles
        self._stats, self._habit_repo, self._habits = stats, habit_repo, habits
        self._intentions, self._clock = intentions, clock

    def _enc(self, text: str | None) -> bytes | None:
        return self._encryptor.encrypt(text)

    def _dec(self, blob: bytes | None) -> str | None:
        try:
            return self._encryptor.decrypt(blob)
        except ValueError as exc:
            raise DataIntegrityError(str(exc)) from exc

    # ------------------------------------------------------------------ journal
    async def list_journal(self, user_id: UUID, days: int) -> list[dict]:
        if not 1 <= days <= 60:
            raise ValidationError("days must be between 1 and 60.")
        today = await self._profiles.today(user_id)
        start = today - timedelta(days=days - 1)
        texts = {d: (self._dec(b) or "") for d, b in await self._repo.journal_rows(user_id, start, today)}
        stickers = await self._repo.stickers(user_id, start, today)
        return [
            {"entry_date": d, "text": texts.get(d, ""), "sticker": stickers.get(d)}
            for d in sorted(set(texts) | set(stickers), reverse=True)
            if texts.get(d) or stickers.get(d)
        ]

    async def put_journal(self, user_id: UUID, day: date, text: str, sticker: str | None) -> dict:
        today = await self._profiles.today(user_id)
        if day not in (today, today - timedelta(days=1)):
            raise ValidationError("You can add a note for today or yesterday.")
        body = text.strip()
        if len(body) > JOURNAL_MAX:
            raise ValidationError(f"That note is too long (max {JOURNAL_MAX} characters).")
        if sticker is not None and sticker not in STICKERS:
            raise ValidationError("Pick one of the stickers on offer.")
        now = self._clock()
        await self._repo.upsert_journal(user_id, day, self._enc(body) if body else None, now)
        if sticker:
            await self._repo.upsert_sticker(user_id, day, sticker, now)
        else:
            await self._repo.delete_sticker(user_id, day)
        return {"entry_date": day, "text": body, "sticker": sticker}

    # ------------------------------------------------------------------ identity
    async def get_identity(self, user_id: UUID, week_start: date | None) -> dict | None:
        row = await self._repo.get_identity(user_id)
        if row is None:
            return None
        today = await self._profiles.today(user_id)
        start = week_start if week_start is not None else today - timedelta(days=6)
        end = week_start + timedelta(days=6) if week_start is not None else today
        return {
            "sentence": self._dec(row.sentence_encrypted) or "",
            "matters": self._dec(row.matters_encrypted) or "",
            "why_now": self._dec(row.why_now_encrypted) or "",
            "importance": row.importance,
            "confidence": row.confidence,
            "votes": await self._repo.count_confirmed(user_id, start, end),   # each confirmed check-in is a vote
            "updated_at": row.updated_at,
        }

    async def put_identity(
        self, user_id: UUID, matters: str, why_now: str, importance: int, confidence: int, sentence: str,
    ) -> dict:
        matters = clean_text(matters, "What matters", 200)
        why_now = clean_text(why_now, "Why now", 300)
        sentence = clean_text(sentence, "Your sentence", 200)
        if not (0 <= importance <= 10 and 0 <= confidence <= 10):
            raise ValidationError("Importance and confidence go from 0 to 10.")
        await self._repo.upsert_identity(
            user_id, self._enc(matters), self._enc(why_now), importance, confidence, self._enc(sentence), self._clock(),
        )
        return await self.get_identity(user_id, None)  # type: ignore[return-value]

    async def delete_identity(self, user_id: UUID) -> None:
        await self._repo.delete_identity(user_id)

    # ------------------------------------------------------------------ prompt slot + habit check-up
    async def prompt(self, user_id: UUID) -> dict:
        autopsy = await self._current_autopsy(user_id)
        identity_due = (
            await self._repo.get_identity(user_id) is None
            and await self._repo.count_confirmed(user_id, None, None) >= IDENTITY_MIN_CHECKINS
        )
        return {"autopsy": autopsy, "identity_due": identity_due}

    async def _current_autopsy(self, user_id: UUID) -> dict | None:
        today = await self._profiles.today(user_id)
        habits = {h.id: h for h in await self._habit_repo.list_active_habits(user_id)}
        row = await self._repo.get_open_autopsy(user_id)
        if row is not None and row.habit_id not in habits:   # archived since it opened
            await self._repo.resolve_autopsy(row, "dismissed", None, {}, today, self._clock())
            row = None
        if row is None:
            row = await self._detect(user_id, today, habits)
        if row is None:
            return None
        habit = habits[row.habit_id]
        ident = await self._repo.get_identity(user_id)
        lighter = _lighter(habit.target_frequency)
        return {
            "id": row.id, "habit_id": habit.id, "habit_name": habit.name,
            "consistency_pct": float(row.consistency_pct or 0.0), "window_days": AUTOPSY_WINDOW_DAYS,
            "floor_text": habit.floor_text, "current_label": _label(habit.target_frequency),
            "lighter_label": _label(lighter) if lighter else None,
            "identity_sentence": self._dec(ident.sentence_encrypted) if ident else None,
            "identity_confidence": ident.confidence if ident else None,
        }

    async def _detect(self, user_id: UUID, today: date, habits: dict):
        """A habit that has existed 3+ weeks, had enough scheduled days (pauses already excluded by the stats
        engine) and was mostly missed. The worst one wins; one check-up at a time."""
        if not habits:
            return None
        cooling = await self._repo.cooldown_habits(user_id, today)
        old_enough = self._clock() - timedelta(days=AUTOPSY_WINDOW_DAYS)
        _, items, _ = await self._stats.consistency(user_id, today, AUTOPSY_WINDOW_DAYS)
        failing = [
            c for c in items
            if c.habit_id in habits and c.habit_id not in cooling
            and habits[c.habit_id].created_at <= old_enough
            and c.consistency_pct is not None and c.expected >= AUTOPSY_MIN_EXPECTED
            and c.consistency_pct < AUTOPSY_FAIL_BELOW_PCT
        ]
        if not failing:
            return None
        worst = min(failing, key=lambda c: c.consistency_pct)
        await self._repo.open_autopsy(user_id, worst.habit_id, float(worst.consistency_pct), today, self._clock())
        return await self._repo.get_open_autopsy(user_id)

    async def apply_autopsy(
        self, user_id: UUID, autopsy_id: UUID, reason: str, floor_text: str | None, cue: str | None,
        choice: str | None,
    ) -> dict:
        if reason not in REASONS:
            raise ValidationError(f"reason must be one of {REASONS}.")
        row = await self._repo.get_autopsy(user_id, autopsy_id)
        if row is None:
            raise NotFoundError("No check-up like that.")
        if row.status != "open":
            raise ConflictError("This check-up is already done.")
        habit = await self._habit_repo.get_habit(user_id, row.habit_id)
        if habit is None or not habit.is_active:
            raise NotFoundError("That habit is no longer active.")

        fix: dict = {}
        if reason == "too_big":
            floor = clean_text(floor_text or "", "The tiny version", 120)
            lighter = _lighter(habit.target_frequency)
            await self._habits.update_habit(
                user_id, habit.id, None, None, target_frequency=lighter, tier_text={"floor_text": floor},
            )
            fix = {"floor_text": floor, "frequency": _label(lighter) if lighter else None}
            message = f"Done. “{habit.name}” now has a tiny version: {floor}."
        elif reason in ("wrong_time", "wrong_trigger"):
            label = "When it fits" if reason == "wrong_time" else "What comes right before"
            clean_cue = clean_text(cue or "", label, 200)
            await self._intentions.create(user_id, "habit", habit.id, clean_cue, habit.name)
            fix = {"cue": clean_cue}
            message = "Saved. That's the new plan for this habit."
        else:
            if choice not in ("archive", "keep"):
                raise ValidationError("Choose to archive it or keep it.")
            if choice == "archive":
                await self._habits.update_habit(user_id, habit.id, None, True)
                message = f"Let go of “{habit.name}”. Room for what matters."
            else:
                message = "Kept. I'll leave it alone for a while."
            fix = {"choice": choice}

        today = await self._profiles.today(user_id)
        await self._repo.resolve_autopsy(
            row, "applied", reason, fix, today + timedelta(days=AUTOPSY_DONE_DAYS), self._clock(),
        )
        return {"message": message}

    async def defer_autopsy(self, user_id: UUID, autopsy_id: UUID, skip: bool) -> None:
        row = await self._repo.get_autopsy(user_id, autopsy_id)
        if row is None:
            raise NotFoundError("No check-up like that.")
        if row.status != "open":
            return   # already handled: idempotent
        today = await self._profiles.today(user_id)
        days = AUTOPSY_SKIP_DAYS if skip else AUTOPSY_LATER_DAYS
        await self._repo.resolve_autopsy(
            row, "dismissed" if skip else "snoozed", None, {}, today + timedelta(days=days), self._clock(),
        )

    # ------------------------------------------------------------------ notes to future self
    def _future_view(self, row, with_audio: bool = False) -> dict:
        view = {
            "id": row.id, "text": self._dec(row.text_encrypted), "has_audio": row.audio_encrypted is not None,
            "duration_s": row.duration_s, "send_at": _hhmm(row.send_at), "active": row.active,
            "audio_b64": None, "audio_mime": None,
        }
        if with_audio and row.audio_encrypted is not None:
            view["audio_b64"], view["audio_mime"] = self._dec(row.audio_encrypted), row.audio_mime
        return view

    async def list_future(self, user_id: UUID) -> list[dict]:
        return [self._future_view(r) for r in await self._repo.list_future(user_id)]

    async def get_future(self, user_id: UUID, message_id: UUID) -> dict:
        row = await self._repo.get_future(user_id, message_id)
        if row is None:
            raise NotFoundError("No note like that.")
        return self._future_view(row, with_audio=True)

    async def create_future(
        self, user_id: UUID, text: str | None, audio_b64: str | None, audio_mime: str | None,
        duration_s: int | None, send_at: str | None,
    ) -> dict:
        body = (text or "").strip()
        if len(body) > FUTURE_TEXT_MAX:
            raise ValidationError(f"Keep the text under {FUTURE_TEXT_MAX} characters.")
        if not body and not audio_b64:
            raise ValidationError("Write something or record something.")
        audio_enc: bytes | None = None
        mime: str | None = None
        if audio_b64:
            mime = (audio_mime or "").split(";")[0].strip().lower()
            if mime not in _AUDIO_MIMES:
                raise ValidationError("That audio format isn't supported.")
            try:
                raw = base64.b64decode(audio_b64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValidationError("The recording couldn't be read.") from exc
            if not raw or len(raw) > FUTURE_AUDIO_MAX_BYTES:
                raise ValidationError("That recording is too long. Keep it to about 20 seconds.")
            if duration_s is None or not 1 <= duration_s <= FUTURE_AUDIO_MAX_SECONDS:
                raise ValidationError("A voice note is 1 to 25 seconds.")
            audio_enc = self._enc(audio_b64)
        slot = _parse_hhmm(send_at)
        if await self._repo.count_active_future(user_id) >= FUTURE_MAX_ACTIVE:
            raise ValidationError(f"You can keep {FUTURE_MAX_ACTIVE} active notes. Pause or delete one first.")
        row = await self._repo.add_future(
            user_id, self._enc(body) if body else None, audio_enc, mime, duration_s if audio_enc else None, slot,
            self._clock(),
        )
        return self._future_view(row)

    async def set_future_active(self, user_id: UUID, message_id: UUID, active: bool) -> None:
        if active and await self._repo.count_active_future(user_id) >= FUTURE_MAX_ACTIVE:
            raise ValidationError(f"You can keep {FUTURE_MAX_ACTIVE} active notes.")
        if not await self._repo.set_future_active(user_id, message_id, active, self._clock()):
            raise NotFoundError("No note like that.")

    async def delete_future(self, user_id: UUID, message_id: UUID) -> None:
        if not await self._repo.delete_future(user_id, message_id):
            raise NotFoundError("No note like that.")

    async def mark_future_played(self, user_id: UUID, message_id: UUID) -> None:
        if await self._repo.get_future(user_id, message_id) is None:
            raise NotFoundError("No note like that.")
        await self._repo.mark_future_played(user_id, message_id, self._clock())
