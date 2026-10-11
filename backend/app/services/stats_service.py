from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from app.exceptions import ValidationError
from app.repositories.habit_repository import HabitRepository
from app.repositories.pause_repository import PauseRepository
from app.repositories.screen_time_repository import ScreenTimeRepository
from app.repositories.sleep_repository import SleepRepository
from app.repositories.study_repository import StudySessionRepository
from app.repositories.urge_repository import UrgeRepository
from app.services.chain_service import NONE, ChainDay, build_chain, study_states_by_day, urge_states_by_day
from app.services.consistency_service import HabitConsistency, compute_habit_consistency, overall_consistency
from app.services.pattern_service import Pattern, find_patterns
from app.services.pause_days import split_pause_days
from app.services.profile_service import ProfileService

_MAX_WINDOW_DAYS = 400


class StatsService:

    def __init__(
        self,
        habit_repo: HabitRepository,
        sleep_repo: SleepRepository,
        screen_repo: ScreenTimeRepository,
        profiles: ProfileService,
        study_repo: StudySessionRepository | None = None,
        urge_repo: UrgeRepository | None = None,
        pause_repo: PauseRepository | None = None,
    ):
        self._habits = habit_repo
        self._sleep = sleep_repo
        self._screen = screen_repo
        self._profiles = profiles
        self._study = study_repo
        self._urges = urge_repo
        self._pauses = pause_repo

    async def _resolve_end(self, user_id: UUID, end_date: date | None) -> date:
        return end_date or await self._profiles.today(user_id)

    async def _pause_sets(
        self, user_id: UUID, start: date, end: date
    ) -> tuple[frozenset[date], dict[UUID, frozenset[date]]]:
        if self._pauses is None:
            return frozenset(), {}
        return split_pause_days(await self._pauses.list_overlapping(user_id, start, end), start, end)

    async def consistency(
        self, user_id: UUID, end_date: date | None, window_days: int
    ) -> tuple[date, list[HabitConsistency], float | None]:
        if not 1 <= window_days <= _MAX_WINDOW_DAYS:
            raise ValidationError(f"window_days must be between 1 and {_MAX_WINDOW_DAYS}.")
        end = await self._resolve_end(user_id, end_date)
        habits = await self._habits.list_active_habits(user_id)
        start = end - timedelta(days=window_days - 1)
        logs = await self._habits.get_logs_in_range(user_id, [h.id for h in habits], start, end)
        global_days, by_habit = await self._pause_sets(user_id, start, end)
        items = [
            compute_habit_consistency(h, logs, end, window_days, global_days | by_habit.get(h.id, frozenset()))
            for h in habits
        ]
        return end, items, overall_consistency(items)

    async def chain(self, user_id: UUID, end_date: date | None, days: int) -> tuple[date, list[ChainDay]]:
        if not 1 <= days <= _MAX_WINDOW_DAYS:
            raise ValidationError(f"days must be between 1 and {_MAX_WINDOW_DAYS}.")
        end = await self._resolve_end(user_id, end_date)
        start = end - timedelta(days=days - 1)
        habits = await self._habits.list_active_habits(user_id)
        # +6 days of lead-in so n_per_week quota context is correct on the first rows.
        habit_logs = await self._habits.get_logs_in_range(
            user_id, [h.id for h in habits], start - timedelta(days=6), end
        )
        sleep_logs = await self._sleep.list_logs_in_range(user_id, start, end)
        screen_logs = await self._screen.list_logs_in_range(user_id, start, end)
        study_states = (
            study_states_by_day(await self._study.list_in_range(user_id, start, end))
            if self._study else None
        )
        urge_states = (
            urge_states_by_day(await self._urges.list_in_range(user_id, start, end))
            if self._urges else None
        )
        rows = build_chain(
            habits,
            habit_logs,
            sleep_logs,
            screen_logs,
            start,
            end,
            study_by_day=study_states,
            urge_by_day=urge_states,
        )
        global_days, by_habit = await self._pause_sets(user_id, start, end)
        real_logs = {(l.habit_id, l.log_date) for l in habit_logs if not l.is_default}

        # Per-habit pauses: re-evaluate the day's habit state WITHOUT the habits paused that day.
        # (A paused habit the user logged anyway stays in: real data is never wiped.)
        affected = {d for days_ in by_habit.values() for d in days_}
        if affected:
            for row in rows:
                if row.day not in affected:
                    continue
                active = [
                    h for h in habits
                    if row.day not in by_habit.get(h.id, frozenset()) or (h.id, row.day) in real_logs
                ]
                single = build_chain(active, habit_logs, [], [], row.day, row.day)[0]
                for attr in ("habits", "habit_ratio", "habits_defaulted"):
                    if hasattr(single, attr):
                        setattr(row, attr, getattr(single, attr))

        # Global pauses: an UNLOGGED habit day must never read as a slip.
        if global_days:
            real_habit_days = {d for (_, d) in real_logs}
            for row in rows:
                if row.day in global_days and row.day not in real_habit_days:
                    row.habits = NONE
                    row.habit_ratio = None

        return end, rows

    async def patterns(self, user_id: UUID, end_date: date | None, days: int) -> tuple[date, list[Pattern]]:
        end, chain = await self.chain(user_id, end_date, days)
        return end, find_patterns(chain)
