from __future__ import annotations

from datetime import date
from uuid import UUID

from app.domain import HabitDefinition, HabitLog, HabitStatus, TargetFrequency
from app.exceptions import NotFoundError
from app.repositories.habit_repository import HabitRepository


class HabitsService:
    def __init__(self, habit_repo: HabitRepository):
        self._habits = habit_repo

    async def create_habit(
        self, user_id: UUID, name: str, target_frequency: TargetFrequency
    ) -> HabitDefinition:
        return await self._habits.create_habit(user_id, name.strip(), target_frequency)

    async def list_habits(self, user_id: UUID) -> list[HabitDefinition]:
        return await self._habits.list_active_habits(user_id)

    async def log_habit(
        self,
        user_id: UUID,
        habit_id: UUID,
        log_date: date,
        status: HabitStatus,
        note: str | None,
    ) -> HabitLog:
        """
        Logs (or corrects — this is an upsert) a habit's status for a given
        date. Explicitly re-fetches the habit scoped to user_id first: the
        habit_logs table's foreign key only guarantees habit_id references
        *some* real habit_definitions row, not that it belongs to this
        user. Without this check, a caller who somehow obtained another
        user's habit_id could write a log against it. Postgres RLS is the
        second line of defense here, not the only one — see
        SqlAlchemyHabitRepository's docstring.
        """
        habit = await self._habits.get_habit(user_id, habit_id)
        if habit is None:
            raise NotFoundError(f"No habit {habit_id} for this user.")

        log = HabitLog(
            habit_id=habit_id,
            user_id=user_id,
            log_date=log_date,
            status=status,
            note=note,
            is_default=False,  # an explicit log call is, by definition, not a default
        )
        return await self._habits.upsert_log(log)
