from __future__ import annotations

from datetime import date
from uuid import UUID

from app.domain import Pause


class InMemoryPauseRepository:

    def __init__(self):
        self._rows: dict[UUID, Pause] = {}

    async def create(self, pause: Pause) -> Pause:
        self._rows[pause.id] = pause
        return pause

    async def get(self, user_id: UUID, pause_id: UUID) -> Pause | None:
        p = self._rows.get(pause_id)
        return p if p is not None and p.user_id == user_id else None

    async def list(
        self, user_id: UUID, ending_on_or_after: date | None = None, habit_id: UUID | None = None
    ) -> list[Pause]:
        rows = [
            p for p in self._rows.values()
            if p.user_id == user_id
            and (ending_on_or_after is None or p.end_date >= ending_on_or_after)
            and (habit_id is None or p.habit_id == habit_id)
        ]
        return sorted(rows, key=lambda p: p.start_date)

    async def list_overlapping(
        self, user_id: UUID, start: date, end: date, global_only: bool = False
    ) -> list[Pause]:
        rows = [
            p for p in self._rows.values()
            if p.user_id == user_id
            and p.start_date <= end
            and p.end_date >= start
            and (not global_only or p.habit_id is None)
        ]
        return sorted(rows, key=lambda p: p.start_date)

    async def set_end(self, user_id: UUID, pause_id: UUID, end_date: date) -> Pause | None:
        p = self._rows.get(pause_id)
        if p is None or p.user_id != user_id:
            return None
        p.end_date = end_date
        return p

    async def delete(self, user_id: UUID, pause_id: UUID) -> bool:
        p = self._rows.get(pause_id)
        if p is None or p.user_id != user_id:
            return False
        del self._rows[pause_id]
        return True
