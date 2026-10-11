"""
Pauses: "don't judge these days" (sick, travel, exam week), for everything or for ONE habit.
A pause removes the expectation, never the history: logs made during a pause are kept as normal data.
habit_id None -> consistency, chain, check-in rows, plan reminders, daily reminders
habit_id = X -> habit X only: its consistency, its chain contribution, its check-in row, its plan reminders
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

from app.dates import Clock, utc_now
from app.domain import Pause
from app.exceptions import NotFoundError, ValidationError
from app.repositories.habit_repository import HabitRepository
from app.repositories.pause_repository import PauseRepository
from app.services.profile_service import ProfileService

MAX_PAUSE_DAYS = 60
MAX_BACKDATE_DAYS = 30
MAX_AHEAD_DAYS = 90
MAX_OPEN_PAUSES = 24


class PausesService:

    def __init__(
        self,
        repo: PauseRepository,
        profiles: ProfileService,
        clock: Clock = utc_now,
        habits: HabitRepository | None = None,
    ):
        self._repo = repo
        self._profiles = profiles
        self._clock = clock
        self._habits = habits

    async def create(self, user_id: UUID, start: date, end: date, habit_id: UUID | None = None) -> Pause:
        today = await self._profiles.today(user_id)
        if end < start:
            raise ValidationError("A pause can't end before it starts.")
        if (end - start).days + 1 > MAX_PAUSE_DAYS:
            raise ValidationError(f"A pause can cover at most {MAX_PAUSE_DAYS} days.")
        if start < today - timedelta(days=MAX_BACKDATE_DAYS):
            raise ValidationError(f"You can pause at most {MAX_BACKDATE_DAYS} days back.")
        if end > today + timedelta(days=MAX_AHEAD_DAYS):
            raise ValidationError(f"You can plan a pause at most {MAX_AHEAD_DAYS} days ahead.")
        if habit_id is not None:
            habit = await self._habits.get_habit(user_id, habit_id) if self._habits is not None else None
            if habit is None or not habit.is_active:
                raise NotFoundError(f"No active habit {habit_id} for this user.")
        if len(await self._repo.list(user_id, ending_on_or_after=today)) >= MAX_OPEN_PAUSES:
            raise ValidationError("Too many open pauses. Delete one you don't need.")
        return await self._repo.create(
            Pause(
                id=uuid4(),
                user_id=user_id,
                start_date=start,
                end_date=end,
                created_at=self._clock(),
                habit_id=habit_id,
            )
        )

    async def list(self, user_id: UUID, include_past: bool = False, habit_id: UUID | None = None) -> list[Pause]:
        today = await self._profiles.today(user_id)
        cutoff = None if (include_past or habit_id is not None) else today
        return await self._repo.list(user_id, cutoff, habit_id)

    async def end_now(self, user_id: UUID, pause_id: UUID) -> Pause:
        """I'm back early: the pause ends today."""
        today = await self._profiles.today(user_id)
        pause = await self._repo.get(user_id, pause_id)
        if pause is None:
            raise NotFoundError("No pause found for this user.")
        if not pause.covers(today):
            raise ValidationError("Only a pause that's running right now can be ended. Delete it instead.")
        updated = await self._repo.set_end(user_id, pause_id, today)
        assert updated is not None
        return updated

    async def delete(self, user_id: UUID, pause_id: UUID) -> None:
        if not await self._repo.delete(user_id, pause_id):
            raise NotFoundError("No pause found for this user.")
