from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import ScreenTimeLog, ScreenTimeSource
from app.models import ScreenTimeLogORM


class ScreenTimeRepository(Protocol):
    async def upsert_log(self, log: ScreenTimeLog) -> ScreenTimeLog: ...

    async def get_log(self, user_id: UUID, log_date: date) -> ScreenTimeLog | None: ...

    async def list_logs_in_range(
        self, user_id: UUID, start_date: date, end_date: date
    ) -> list[ScreenTimeLog]: ...


def _log_from_orm(row: ScreenTimeLogORM) -> ScreenTimeLog:
    return ScreenTimeLog(
        user_id=row.user_id,
        log_date=row.log_date,
        total_minutes=row.total_minutes,
        source=ScreenTimeSource(row.source),
        category_breakdown=row.category_breakdown,
    )


class SqlAlchemyScreenTimeRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert_log(self, log: ScreenTimeLog) -> ScreenTimeLog:
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(ScreenTimeLogORM)
            .values(
                user_id=log.user_id,
                log_date=log.log_date,
                total_minutes=log.total_minutes,
                source=log.source.value,
                category_breakdown=log.category_breakdown,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="screen_time_logs_user_id_log_date_key",
                set_={
                    "total_minutes": log.total_minutes,
                    "source": log.source.value,
                    "category_breakdown": log.category_breakdown,
                    "updated_at": now,
                },
            )
            .returning(ScreenTimeLogORM)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        row = result.scalar_one()
        return _log_from_orm(row)

    async def get_log(self, user_id: UUID, log_date: date) -> ScreenTimeLog | None:
        stmt = select(ScreenTimeLogORM).where(
            ScreenTimeLogORM.user_id == user_id, ScreenTimeLogORM.log_date == log_date
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _log_from_orm(row) if row else None

    async def list_logs_in_range(
        self, user_id: UUID, start_date: date, end_date: date
    ) -> list[ScreenTimeLog]:
        stmt = (
            select(ScreenTimeLogORM)
            .where(
                ScreenTimeLogORM.user_id == user_id,
                ScreenTimeLogORM.log_date >= start_date,
                ScreenTimeLogORM.log_date <= end_date,
            )
            .order_by(ScreenTimeLogORM.log_date)
        )
        result = await self._session.execute(stmt)
        return [_log_from_orm(row) for row in result.scalars().all()]
