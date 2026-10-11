from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Pause
from app.models import PauseORM


class PauseRepository(Protocol):

    async def create(self, pause: Pause) -> Pause:
        ...

    async def get(self, user_id: UUID, pause_id: UUID) -> Pause | None:
        ...

    async def list(
        self, user_id: UUID, ending_on_or_after: date | None = None, habit_id: UUID | None = None
    ) -> list[Pause]:
        ...

    async def list_overlapping(
        self, user_id: UUID, start: date, end: date, global_only: bool = False
    ) -> list[Pause]:
        """global_only=True returns only pauses that cover everything (habit_id NULL)."""
        ...

    async def set_end(self, user_id: UUID, pause_id: UUID, end_date: date) -> Pause | None:
        ...

    async def delete(self, user_id: UUID, pause_id: UUID) -> bool:
        ...


def _to_domain(row: PauseORM) -> Pause:
    return Pause(
        id=row.id,
        user_id=row.user_id,
        start_date=row.start_date,
        end_date=row.end_date,
        created_at=row.created_at,
        habit_id=row.habit_id,
    )


class SqlAlchemyPauseRepository:

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, pause: Pause) -> Pause:
        self._session.add(
            PauseORM(
                id=pause.id,
                user_id=pause.user_id,
                start_date=pause.start_date,
                end_date=pause.end_date,
                habit_id=pause.habit_id,
                created_at=pause.created_at,
                updated_at=pause.created_at,
            )
        )
        await self._session.flush()
        return pause

    async def get(self, user_id: UUID, pause_id: UUID) -> Pause | None:
        stmt = select(PauseORM).where(PauseORM.id == pause_id, PauseORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def list(
        self, user_id: UUID, ending_on_or_after: date | None = None, habit_id: UUID | None = None
    ) -> list[Pause]:
        stmt = select(PauseORM).where(PauseORM.user_id == user_id)
        if ending_on_or_after is not None:
            stmt = stmt.where(PauseORM.end_date >= ending_on_or_after)
        if habit_id is not None:
            stmt = stmt.where(PauseORM.habit_id == habit_id)
        rows = (await self._session.execute(stmt.order_by(PauseORM.start_date))).scalars().all()
        return [_to_domain(r) for r in rows]

    async def list_overlapping(
        self, user_id: UUID, start: date, end: date, global_only: bool = False
    ) -> list[Pause]:
        stmt = select(PauseORM).where(
            PauseORM.user_id == user_id,
            PauseORM.start_date <= end,
            PauseORM.end_date >= start,
        )
        if global_only:
            stmt = stmt.where(PauseORM.habit_id.is_(None))
        return [_to_domain(r) for r in (await self._session.execute(stmt.order_by(PauseORM.start_date))).scalars().all()]

    async def set_end(self, user_id: UUID, pause_id: UUID, end_date: date) -> Pause | None:
        stmt = select(PauseORM).where(PauseORM.id == pause_id, PauseORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        row.end_date = end_date
        row.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return _to_domain(row)

    async def delete(self, user_id: UUID, pause_id: UUID) -> bool:
        result = await self._session.execute(
            delete(PauseORM).where(PauseORM.id == pause_id, PauseORM.user_id == user_id)
        )
        return (result.rowcount or 0) > 0
