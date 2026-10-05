from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Profile
from app.models import ProfileORM


class ProfileRepository(Protocol):
    async def get_or_create(self, user_id: UUID) -> Profile: ...

    async def set_timezone(self, user_id: UUID, tz_name: str) -> Profile: ...


def _to_domain(row: ProfileORM) -> Profile:
    return Profile(user_id=row.id, timezone=row.timezone, tone_preference=row.tone_preference)


class SqlAlchemyProfileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_row(self, user_id: UUID) -> ProfileORM:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            pg_insert(ProfileORM)
            .values(id=user_id, timezone="UTC", tone_preference="direct", created_at=now, updated_at=now)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        result = await self._session.execute(select(ProfileORM).where(ProfileORM.id == user_id))
        return result.scalar_one()

    async def get_or_create(self, user_id: UUID) -> Profile:
        return _to_domain(await self._get_row(user_id))

    async def set_timezone(self, user_id: UUID, tz_name: str) -> Profile:
        row = await self._get_row(user_id)
        row.timezone = tz_name
        row.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return _to_domain(row)
