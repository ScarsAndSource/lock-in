"""
Pause shortcuts for the habit page: preset buttons, a one-call overview of every habit's
pause state, "quick" pause (extends a running pause instead of stacking duplicates) and
one-tap resume.

Presets are computed from the user's LOCAL today. A preset whose dates equal an earlier one
is dropped (on a Sunday "Until Sunday" would just be "Just today").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from app.dates import Clock, utc_now
from app.domain import Pause
from app.exceptions import NotFoundError, ValidationError
from app.repositories.habit_repository import HabitRepository
from app.repositories.pause_repository import PauseRepository
from app.services.pauses_service import MAX_PAUSE_DAYS, PausesService
from app.services.profile_service import ProfileService

PRESET_KEYS = ("today", "3_days", "this_week", "1_week", "2_weeks")
_LABELS = {
    "today": "Just today",
    "3_days": "3 days",
    "this_week": "Until Sunday",
    "1_week": "1 week",
    "2_weeks": "2 weeks",
}


@dataclass(frozen=True, slots=True)
class Shortcut:
    key: str
    label: str
    start_date: date
    end_date: date

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


@dataclass(slots=True)
class HabitPauseRow:
    habit_id: UUID
    name: str
    state: str  # active | paused | upcoming (this habit's OWN pauses)
    effective_paused: bool  # paused by its own pause OR by a global one
    paused_by: str | None  # "habit" | "all" | None
    pause: Pause | None  # the running per-habit pause, else the next upcoming one


@dataclass(slots=True)
class PauseOverview:
    today: date
    global_pause: Pause | None
    habits: list[HabitPauseRow]


def preset_range(key: str, today: date) -> tuple[date, date]:
    if key == "today":
        return today, today
    if key == "3_days":
        return today, today + timedelta(days=2)
    if key == "this_week":
        return today, today + timedelta(days=6 - today.weekday())  # through Sunday
    if key == "1_week":
        return today, today + timedelta(days=6)
    if key == "2_weeks":
        return today, today + timedelta(days=13)
    raise ValidationError(f"Unknown pause preset {key!r}.")


def shortcut_list(today: date) -> list[Shortcut]:
    out: list[Shortcut] = []
    seen: set[tuple[date, date]] = set()
    for key in PRESET_KEYS:
        start, end = preset_range(key, today)
        if (start, end) in seen:
            continue
        seen.add((start, end))
        out.append(Shortcut(key, _LABELS[key], start, end))
    return out


class PauseShortcutsService:
    def __init__(
        self,
        pauses: PausesService,
        repo: PauseRepository,
        habits: HabitRepository,
        profiles: ProfileService,
        clock: Clock = utc_now,
    ):
        self._pauses, self._repo, self._habits = pauses, repo, habits
        self._profiles, self._clock = profiles, clock

    async def _require_habit(self, user_id: UUID, habit_id: UUID | None) -> None:
        if habit_id is None:
            return
        habit = await self._habits.get_habit(user_id, habit_id)
        if habit is None or not habit.is_active:
            raise NotFoundError(f"No active habit {habit_id} for this user.")

    async def shortcuts(self, user_id: UUID) -> list[Shortcut]:
        return shortcut_list(await self._profiles.today(user_id))

    async def overview(self, user_id: UUID) -> PauseOverview:
        today = await self._profiles.today(user_id)
        habits = await self._habits.list_active_habits(user_id)
        pauses = await self._repo.list(user_id, ending_on_or_after=today)  # running + upcoming, every scope
        global_running = next((p for p in pauses if p.habit_id is None and p.covers(today)), None)
        rows: list[HabitPauseRow] = []
        for h in habits:
            mine = sorted((p for p in pauses if p.habit_id == h.id), key=lambda p: p.start_date)
            running = next((p for p in mine if p.covers(today)), None)
            upcoming = next((p for p in mine if p.start_date > today), None)
            rows.append(HabitPauseRow(
                habit_id=h.id,
                name=h.name,
                state="paused" if running else "upcoming" if upcoming else "active",
                effective_paused=running is not None or global_running is not None,
                paused_by="habit" if running else "all" if global_running else None,
                pause=running or upcoming,
            ))
        return PauseOverview(today, global_running, rows)

    async def quick(self, user_id: UUID, preset: str, habit_id: UUID | None) -> Pause:
        """Pause via a preset. If a same-scope pause is already running, EXTEND it (never stack a
        duplicate); a shorter preset than what's running changes nothing."""
        today = await self._profiles.today(user_id)
        start, end = preset_range(preset, today)
        await self._require_habit(user_id, habit_id)
        running = [
            p for p in await self._repo.list_overlapping(user_id, start, end)
            if p.habit_id == habit_id and p.covers(today)
        ]
        if running:
            base = max(running, key=lambda p: p.end_date)
            if end <= base.end_date:
                return base
            if (end - base.start_date).days + 1 > MAX_PAUSE_DAYS:
                raise ValidationError(f"That would make this pause longer than {MAX_PAUSE_DAYS} days.")
            extended = await self._repo.set_end(user_id, base.id, end)
            assert extended is not None
            return extended
        return await self._pauses.create(user_id, start, end, habit_id)

    async def resume(self, user_id: UUID, habit_id: UUID | None) -> tuple[int, bool]:
        """One tap: count today again. A pause that started earlier ends YESTERDAY; one that starts
        today is removed. Returns (pauses resumed, still_paused_by_a_global_pause)."""
        today = await self._profiles.today(user_id)
        await self._require_habit(user_id, habit_id)
        covering = await self._repo.list_overlapping(user_id, today, today)
        running = [p for p in covering if p.habit_id == habit_id]
        for p in running:
            if p.start_date >= today:
                await self._repo.delete(user_id, p.id)
            else:
                await self._repo.set_end(user_id, p.id, today - timedelta(days=1))
        still_all = habit_id is not None and any(p.habit_id is None for p in covering)
        return len(running), still_all
