from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import IngestToken
from app.models import IngestTokenORM


class IngestTokenRepository(Protocol):
    async def create(self, token: IngestToken) -> IngestToken: ...
    async def get(self, user_id: UUID, token_id: UUID) -> IngestToken | None: ...
    async def list(self, user_id: UUID) -> list[IngestToken]: ...
    async def revoke(self, user_id: UUID, token_id: UUID, now: datetime) -> bool: ...
    async def touch(self, user_id: UUID, token_id: UUID, now: datetime) -> None: ...


def _to_domain(r: IngestTokenORM) -> IngestToken:
    return IngestToken(id=r.id, user_id=r.user_id, label=r.label, created_at=r.created_at,
                       last_used_at=r.last_used_at, revoked_at=r.revoked_at)


class SqlAlchemyIngestTokenRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, token: IngestToken) -> IngestToken:
        self._session.add(IngestTokenORM(
            id=token.id, user_id=token.user_id, label=token.label, created_at=token.created_at,
        ))
        await self._session.flush()
        return token

    async def get(self, user_id: UUID, token_id: UUID) -> IngestToken | None:
        row = (await self._session.execute(
            select(IngestTokenORM).where(IngestTokenORM.id == token_id, IngestTokenORM.user_id == user_id)
        )).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def list(self, user_id: UUID) -> list[IngestToken]:
        rows = (await self._session.execute(
            select(IngestTokenORM).where(IngestTokenORM.user_id == user_id).order_by(IngestTokenORM.created_at.desc())
        )).scalars().all()
        return [_to_domain(r) for r in rows]

    async def revoke(self, user_id: UUID, token_id: UUID, now: datetime) -> bool:
        res = await self._session.execute(
            update(IngestTokenORM)
            .where(IngestTokenORM.id == token_id, IngestTokenORM.user_id == user_id, IngestTokenORM.revoked_at.is_(None))
            .values(revoked_at=now).returning(IngestTokenORM.id)
        )
        return res.scalar_one_or_none() is not None

    async def touch(self, user_id: UUID, token_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(IngestTokenORM).where(IngestTokenORM.id == token_id, IngestTokenORM.user_id == user_id)
            .values(last_used_at=now)
        )
