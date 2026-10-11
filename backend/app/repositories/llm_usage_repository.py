from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LlmUsageORM


class LlmUsageRepository(Protocol):
    async def consume(self, user_id: UUID, day: date, feature: str) -> int:
        """Atomically +1 this feature's calls; returns the user's TOTAL calls for the day afterwards."""
        ...

    async def release(self, user_id: UUID, day: date, feature: str) -> None:
        ...

    async def add_tokens(self, user_id: UUID, day: date, feature: str, tokens: int) -> None:
        ...


class SqlAlchemyLlmUsageRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def consume(self, user_id: UUID, day: date, feature: str) -> int:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            pg_insert(LlmUsageORM)
            .values(
                id=uuid4(),
                user_id=user_id,
                usage_date=day,
                feature=feature,
                calls=1,
                tokens=0,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="llm_usage_user_day_feature",
                set_={"calls": LlmUsageORM.calls + 1, "updated_at": now},
            )
        )
        total = (
            await self._session.execute(
                select(func.coalesce(func.sum(LlmUsageORM.calls), 0)).where(
                    LlmUsageORM.user_id == user_id, LlmUsageORM.usage_date == day
                )
            )
        ).scalar_one()
        return int(total)

    async def release(self, user_id: UUID, day: date, feature: str) -> None:
        await self._session.execute(
            update(LlmUsageORM)
            .where(
                LlmUsageORM.user_id == user_id,
                LlmUsageORM.usage_date == day,
                LlmUsageORM.feature == feature,
            )
            .values(calls=func.greatest(LlmUsageORM.calls - 1, 0))
        )

    async def add_tokens(self, user_id: UUID, day: date, feature: str, tokens: int) -> None:
        await self._session.execute(
            update(LlmUsageORM)
            .where(
                LlmUsageORM.user_id == user_id,
                LlmUsageORM.usage_date == day,
                LlmUsageORM.feature == feature,
            )
            .values(tokens=LlmUsageORM.tokens + tokens)
        )
