from __future__ import annotations

from datetime import date
from uuid import UUID

from app.dates import Clock, assert_loggable_date, utc_now
from app.domain import HabitDefinition, HabitLog, HabitStatus, TargetFrequency
from app.exceptions import NotFoundError, ValidationError
from app.repositories.habit_repository import HabitRepository


class HabitsService:
    def __init__(self, habit_repo: HabitRepository, clock: Clock = utc_now):
        self._habits = habit_repo
        self._clock = clock

    async def create_habit(self, user_id: UUID, name: str, target_frequency: TargetFrequency) -> HabitDefinition:
        if not name.strip():
            raise ValidationError("Habit name can't be blank.")
        return await self._habits.create_habit(user_id, name.strip(), target_frequency)

    async def list_habits(self, user_id: UUID, include_archived: bool = False) -> list[HabitDefinition]:
        if include_archived:
            return await self._habits.list_habits(user_id, include_archived=True)
        return await self._habits.list_active_habits(user_id)

    async def update_habit(
        self, user_id: UUID, habit_id: UUID, name: str | None, archived: bool | None,
        target_frequency: TargetFrequency | None = None,
    ) -> HabitDefinition:
        if name is not None and not name.strip():
            raise ValidationError("Habit name can't be blank.")
        habit = await self._habits.update_habit(
            user_id, habit_id, name.strip() if name is not None else None, archived, self._clock(),
            target_frequency=target_frequency,
        )
        if habit is None:
            raise NotFoundError(f"No habit {habit_id} for this user.")
        return habit

    async def delete_log(self, user_id: UUID, habit_id: UUID, log_date: date) -> None:
        if await self._habits.get_habit(user_id, habit_id) is None:
            raise NotFoundError(f"No habit {habit_id} for this user.")
        if not await self._habits.delete_log(user_id, habit_id, log_date):
            raise NotFoundError("No log for that habit on that date.")

    async def log_habit(
        self, user_id: UUID, habit_id: UUID, log_date: date, status: HabitStatus, note: str | None
    ) -> HabitLog:
        """
        Upsert (also the "fix a wrong default after the fact" mechanism).
        Re-fetches the habit scoped to user_id first: the FK only proves the
        habit exists, not that it's yours. RLS is the second line of defense.
        """
        assert_loggable_date(log_date, self._clock().date())
        habit = await self._habits.get_habit(user_id, habit_id)
        if habit is None:
            raise NotFoundError(f"No habit {habit_id} for this user.")
        return await self._habits.upsert_log(
            HabitLog(habit_id=habit_id, user_id=user_id, log_date=log_date, status=status, note=note, is_default=False)
        )
