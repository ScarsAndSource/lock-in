from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import UrgeLog, UrgeOutcome
from app.models import UrgeLogORM

_DETAIL_COLUMNS = frozenset({
    "intensity", "trigger_context_encrypted", "coping_strategy_encrypted", "note_encrypted",
})


class UrgeRepository(Protocol):
    async def add(self, log: UrgeLog) -> UrgeLog: ...
    async def get(self, user_id: UUID, urge_id: UUID) -> UrgeLog | None: ...
    async def update_detail(self, user_id: UUID, urge_id: UUID, changes: dict) -> UrgeLog | None: ...
    async def delete(self, user_id: UUID, urge_id: UUID) -> bool: ...
    async def list_in_range(self, user_id: UUID, start: date, end: date) -> list[UrgeLog]: ...


def _to_domain(row: UrgeLogORM) -> UrgeLog:
    return UrgeLog(
        id=row.id, user_id=row.user_id, occurred_at=row.occurred_at, log_date=row.log_date,
        outcome=UrgeOutcome(row.outcome), intensity=row.intensity,
        trigger_context_encrypted=row.trigger_context_encrypted,
        coping_strategy_encrypted=row.coping_strategy_encrypted, note_encrypted=row.note_encrypted,
    )


class SqlAlchemyUrgeRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, log: UrgeLog) -> UrgeLog:
        now = datetime.now(timezone.utc)
        row = UrgeLogORM(
            id=log.id, user_id=log.user_id, occurred_at=log.occurred_at, log_date=log.log_date,
            outcome=log.outcome.value, intensity=log.intensity,
            trigger_context_encrypted=log.trigger_context_encrypted,
            coping_strategy_encrypted=log.coping_strategy_encrypted, note_encrypted=log.note_encrypted,
            created_at=now, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)

    async def get(self, user_id: UUID, urge_id: UUID) -> UrgeLog | None:
        stmt = select(UrgeLogORM).where(UrgeLogORM.id == urge_id, UrgeLogORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def update_detail(self, user_id: UUID, urge_id: UUID, changes: dict) -> UrgeLog | None:
        stmt = select(UrgeLogORM).where(UrgeLogORM.id == urge_id, UrgeLogORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        for column, value in changes.items():
            if column not in _DETAIL_COLUMNS:
                raise ValueError(f"Unknown urge column {column!r}")
            setattr(row, column, value)
        row.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return _to_domain(row)

    async def delete(self, user_id: UUID, urge_id: UUID) -> bool:
        result = await self._session.execute(
            delete(UrgeLogORM).where(UrgeLogORM.id == urge_id, UrgeLogORM.user_id == user_id)
        )
        return (result.rowcount or 0) > 0

    async def list_in_range(self, user_id: UUID, start: date, end: date) -> list[UrgeLog]:
        stmt = (
            select(UrgeLogORM)
            .where(UrgeLogORM.user_id == user_id, UrgeLogORM.log_date >= start, UrgeLogORM.log_date <= end)
            .order_by(UrgeLogORM.occurred_at)
        )
        return [_to_domain(r) for r in (await self._session.execute(stmt)).scalars().all()]
