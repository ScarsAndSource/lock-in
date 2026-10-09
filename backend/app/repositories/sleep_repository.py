from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import SleepLog
from app.models import SleepLogORM


class SleepRepository(Protocol):
    async def upsert_log(self, log: SleepLog) -> SleepLog: ...

    async def get_log(self, user_id: UUID, log_date: date) -> SleepLog | None: ...

    async def list_logs_in_range(
        self, user_id: UUID, start_date: date, end_date: date
    ) -> list[SleepLog]: ...

    async def delete_log(self, user_id: UUID, log_date: date) -> bool: ...


def _log_from_orm(row: SleepLogORM) -> SleepLog:
    return SleepLog(
        user_id=row.user_id,
        log_date=row.log_date,
        time_to_bed=row.time_to_bed,
        time_woke=row.time_woke,
        self_rated_quality=row.self_rated_quality,
        is_default=row.is_default,
    )


class SqlAlchemySleepRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert_log(self, log: SleepLog) -> SleepLog:
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(SleepLogORM)
            .values(
                user_id=log.user_id,
                log_date=log.log_date,
                time_to_bed=log.time_to_bed,
                time_woke=log.time_woke,
                self_rated_quality=log.self_rated_quality,
                is_default=log.is_default,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="sleep_logs_user_id_log_date_key",
                set_={
                    "time_to_bed": log.time_to_bed,
                    "time_woke": log.time_woke,
                    "self_rated_quality": log.self_rated_quality,
                    "is_default": log.is_default,
                    "updated_at": now,
                },
            )
            .returning(SleepLogORM)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        row = result.scalar_one()
        return _log_from_orm(row)

    async def get_log(self, user_id: UUID, log_date: date) -> SleepLog | None:
        stmt = select(SleepLogORM).where(
            SleepLogORM.user_id == user_id, SleepLogORM.log_date == log_date
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _log_from_orm(row) if row else None

    async def list_logs_in_range(
        self, user_id: UUID, start_date: date, end_date: date
    ) -> list[SleepLog]:
        stmt = (
            select(SleepLogORM)
            .where(
                SleepLogORM.user_id == user_id,
                SleepLogORM.log_date >= start_date,
                SleepLogORM.log_date <= end_date,
            )
            .order_by(SleepLogORM.log_date)
        )
        result = await self._session.execute(stmt)
        return [_log_from_orm(row) for row in result.scalars().all()]

    async def delete_log(self, user_id: UUID, log_date: date) -> bool:
        result = await self._session.execute(
            delete(SleepLogORM).where(SleepLogORM.user_id == user_id, SleepLogORM.log_date == log_date)
        )
        return (result.rowcount or 0) > 0
