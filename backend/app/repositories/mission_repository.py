from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Mission, MissionStatus
from app.models import MissionORM


class MissionRepository(Protocol):
    async def create(self, mission: Mission) -> Mission: ...

    async def get(self, user_id: UUID, mission_id: UUID) -> Mission | None: ...

    async def get_active(self, user_id: UUID) -> Mission | None: ...

    async def list(self, user_id: UUID) -> list[Mission]: ...

    async def set_status(
        self, user_id: UUID, mission_id: UUID, status: MissionStatus, ended_at: datetime
    ) -> Mission | None: ...


def _to_domain(row: MissionORM) -> Mission:
    return Mission(
        id=row.id, user_id=row.user_id, title=row.title, start_date=row.start_date,
        end_date=row.end_date, status=MissionStatus(row.status),
        created_at=row.created_at, ended_at=row.ended_at,
    )


class SqlAlchemyMissionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, mission: Mission) -> Mission:
        now = datetime.now(timezone.utc)
        row = MissionORM(
            id=mission.id, user_id=mission.user_id, title=mission.title,
            start_date=mission.start_date, end_date=mission.end_date,
            status=mission.status.value, created_at=mission.created_at, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)

    async def get(self, user_id: UUID, mission_id: UUID) -> Mission | None:
        stmt = select(MissionORM).where(MissionORM.id == mission_id, MissionORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def get_active(self, user_id: UUID) -> Mission | None:
        stmt = select(MissionORM).where(MissionORM.user_id == user_id, MissionORM.status == "active")
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def list(self, user_id: UUID) -> list[Mission]:
        stmt = select(MissionORM).where(MissionORM.user_id == user_id).order_by(MissionORM.start_date.desc())
        return [_to_domain(r) for r in (await self._session.execute(stmt)).scalars().all()]

    async def set_status(
        self, user_id: UUID, mission_id: UUID, status: MissionStatus, ended_at: datetime
    ) -> Mission | None:
        stmt = select(MissionORM).where(MissionORM.id == mission_id, MissionORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        row.status = status.value
        row.ended_at = ended_at
        row.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return _to_domain(row)
