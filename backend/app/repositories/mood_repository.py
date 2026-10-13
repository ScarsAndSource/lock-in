from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import MoodLog
from app.models import MoodLogORM


class MoodRepository(Protocol):
    async def upsert_log(self, log: MoodLog) -> MoodLog: ...

    async def get_log(self, user_id: UUID, log_date: date) -> MoodLog | None: ...

    async def list_logs_in_range(self, user_id: UUID, start_date: date, end_date: date) -> list[MoodLog]: ...

    async def delete_log(self, user_id: UUID, log_date: date) -> bool: ...


def _log_from_orm(row: MoodLogORM) -> MoodLog:
    return MoodLog(user_id=row.user_id, log_date=row.log_date, valence=row.valence, energy=row.energy)


class SqlAlchemyMoodRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert_log(self, log: MoodLog) -> MoodLog:
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(MoodLogORM)
            .values(
                user_id=log.user_id, log_date=log.log_date, valence=log.valence, energy=log.energy,
                created_at=now, updated_at=now,
            )
            .on_conflict_do_update(
                constraint="mood_logs_user_id_log_date_key",
                set_={"valence": log.valence, "energy": log.energy, "updated_at": now},
            )
            .returning(MoodLogORM)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return _log_from_orm(result.scalar_one())

    async def get_log(self, user_id: UUID, log_date: date) -> MoodLog | None:
        stmt = select(MoodLogORM).where(MoodLogORM.user_id == user_id, MoodLogORM.log_date == log_date)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _log_from_orm(row) if row else None

    async def list_logs_in_range(self, user_id: UUID, start_date: date, end_date: date) -> list[MoodLog]:
        stmt = (
            select(MoodLogORM)
            .where(MoodLogORM.user_id == user_id, MoodLogORM.log_date >= start_date, MoodLogORM.log_date <= end_date)
            .order_by(MoodLogORM.log_date)
        )
        return [_log_from_orm(row) for row in (await self._session.execute(stmt)).scalars().all()]

    async def delete_log(self, user_id: UUID, log_date: date) -> bool:
        result = await self._session.execute(
            delete(MoodLogORM).where(MoodLogORM.user_id == user_id, MoodLogORM.log_date == log_date)
        )
        return (result.rowcount or 0) > 0
