from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import WeeklyRetro
from app.models import WeeklyRetroORM


class RetroRepository(Protocol):
    async def create(self, retro: WeeklyRetro) -> WeeklyRetro | None: ...
    async def get_by_week(self, user_id: UUID, week_start: date) -> WeeklyRetro | None: ...
    async def latest(self, user_id: UUID) -> WeeklyRetro | None: ...
    async def list(self, user_id: UUID, limit: int) -> list[WeeklyRetro]: ...
    async def mark_completed(self, user_id: UUID, retro_id: UUID, now: datetime) -> WeeklyRetro | None: ...


def _to_domain(row: WeeklyRetroORM) -> WeeklyRetro:
    return WeeklyRetro(
        id=row.id, user_id=row.user_id, week_start=row.week_start, week_end=row.week_end,
        generated_at=row.generated_at, narrative=row.narrative, next_step=row.next_step,
        summary=row.summary, evidence_refs=row.evidence_refs, narrated=row.narrated,
        voice_version=row.voice_version, model=row.model, completed_at=row.completed_at,
    )


class SqlAlchemyRetroRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, retro: WeeklyRetro) -> WeeklyRetro | None:
        """None if this (user, week) already exists — two concurrent generators can't double-insert."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            pg_insert(WeeklyRetroORM)
            .values(
                id=retro.id, user_id=retro.user_id, week_start=retro.week_start, week_end=retro.week_end,
                generated_at=retro.generated_at, narrative=retro.narrative, next_step=retro.next_step,
                summary=retro.summary, evidence_refs=retro.evidence_refs, narrated=retro.narrated,
                voice_version=retro.voice_version, model=retro.model, created_at=now, updated_at=now,
            )
            .on_conflict_do_nothing(constraint="weekly_retros_user_week_key")
            .returning(WeeklyRetroORM.id)
        )
        if result.scalar_one_or_none() is None:
            return None
        return await self.get_by_week(retro.user_id, retro.week_start)

    async def get_by_week(self, user_id: UUID, week_start: date) -> WeeklyRetro | None:
        stmt = select(WeeklyRetroORM).where(
            WeeklyRetroORM.user_id == user_id, WeeklyRetroORM.week_start == week_start
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def latest(self, user_id: UUID) -> WeeklyRetro | None:
        rows = await self.list(user_id, 1)
        return rows[0] if rows else None

    async def list(self, user_id: UUID, limit: int) -> list[WeeklyRetro]:
        stmt = (
            select(WeeklyRetroORM).where(WeeklyRetroORM.user_id == user_id)
            .order_by(WeeklyRetroORM.week_start.desc()).limit(limit)
        )
        return [_to_domain(r) for r in (await self._session.execute(stmt)).scalars().all()]

    async def mark_completed(self, user_id: UUID, retro_id: UUID, now: datetime) -> WeeklyRetro | None:
        stmt = select(WeeklyRetroORM).where(
            WeeklyRetroORM.id == retro_id, WeeklyRetroORM.user_id == user_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        row.completed_at = now
        row.updated_at = now
        await self._session.flush()
        return _to_domain(row)
