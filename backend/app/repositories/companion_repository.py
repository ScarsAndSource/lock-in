"""
Ledger of actionable pushes that were sent (migration 016).

reserve() is the idempotency gate: it inserts the row BEFORE the push goes out, and the unique (user_id, key)
constraint means a second cron run (or a retry) can never send the same moment twice. A push that did not reach any
device is release()d so the next run may try again. mark_acted() is atomic and single-use: only the first caller wins.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CompanionPush
from app.models import CompanionPushORM


class CompanionRepository(Protocol):
    async def reserve(self, push: CompanionPush) -> bool: ...                       # False = key already used
    async def release(self, user_id: UUID, push_id: UUID) -> None: ...
    async def list_since(self, user_id: UUID, since: datetime) -> list[CompanionPush]: ...
    async def mark_acted(self, user_id: UUID, push_id: UUID, action: str, now: datetime) -> CompanionPush | None: ...
    async def prune(self, user_id: UUID, before: datetime) -> int: ...


def _to_domain(row: CompanionPushORM) -> CompanionPush:
    return CompanionPush(
        id=row.id, user_id=row.user_id, kind=row.kind, key=row.key, local_date=row.local_date,
        sent_at=row.sent_at, acted_at=row.acted_at, action=row.action,
    )


class SqlAlchemyCompanionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def reserve(self, push: CompanionPush) -> bool:
        stmt = (
            pg_insert(CompanionPushORM)
            .values(
                id=push.id, user_id=push.user_id, kind=push.kind, key=push.key, local_date=push.local_date,
                sent_at=push.sent_at,
            )
            .on_conflict_do_nothing(constraint="companion_pushes_user_key")
            .returning(CompanionPushORM.id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def release(self, user_id: UUID, push_id: UUID) -> None:
        await self._session.execute(
            delete(CompanionPushORM).where(CompanionPushORM.user_id == user_id, CompanionPushORM.id == push_id)
        )

    async def list_since(self, user_id: UUID, since: datetime) -> list[CompanionPush]:
        stmt = (
            select(CompanionPushORM)
            .where(CompanionPushORM.user_id == user_id, CompanionPushORM.sent_at >= since)
            .order_by(CompanionPushORM.sent_at)
        )
        return [_to_domain(r) for r in (await self._session.execute(stmt)).scalars().all()]

    async def mark_acted(self, user_id: UUID, push_id: UUID, action: str, now: datetime) -> CompanionPush | None:
        stmt = (
            update(CompanionPushORM)
            .where(
                CompanionPushORM.id == push_id, CompanionPushORM.user_id == user_id,
                CompanionPushORM.acted_at.is_(None),
            )
            .values(acted_at=now, action=action[:32])
            .returning(CompanionPushORM)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def prune(self, user_id: UUID, before: datetime) -> int:
        result = await self._session.execute(
            delete(CompanionPushORM).where(CompanionPushORM.user_id == user_id, CompanionPushORM.sent_at < before)
        )
        return result.rowcount or 0
