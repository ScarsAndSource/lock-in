from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import DailyCheckin
from app.models import DailyCheckinORM


class CheckinRepository(Protocol):
    async def get(self, user_id: UUID, checkin_date: date) -> DailyCheckin | None: ...

    async def upsert(self, checkin: DailyCheckin) -> DailyCheckin: ...


def _checkin_from_orm(row: DailyCheckinORM) -> DailyCheckin:
    return DailyCheckin(
        user_id=row.user_id,
        checkin_date=row.checkin_date,
        journal_encrypted=row.journal_encrypted,
        defaults_applied=row.defaults_applied,
        confirmed_at=row.confirmed_at,
    )


class SqlAlchemyCheckinRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, user_id: UUID, checkin_date: date) -> DailyCheckin | None:
        stmt = select(DailyCheckinORM).where(
            DailyCheckinORM.user_id == user_id,
            DailyCheckinORM.checkin_date == checkin_date,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _checkin_from_orm(row) if row else None

    async def upsert(self, checkin: DailyCheckin) -> DailyCheckin:
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(DailyCheckinORM)
            .values(
                user_id=checkin.user_id,
                checkin_date=checkin.checkin_date,
                journal_encrypted=checkin.journal_encrypted,
                defaults_applied=checkin.defaults_applied,
                confirmed_at=checkin.confirmed_at,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="daily_checkins_user_id_checkin_date_key",
                set_={
                    "journal_encrypted": checkin.journal_encrypted,
                    "defaults_applied": checkin.defaults_applied,
                    "confirmed_at": checkin.confirmed_at,
                    "updated_at": now,
                },
            )
            .returning(DailyCheckinORM)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        row = result.scalar_one()
        return _checkin_from_orm(row)
