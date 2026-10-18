from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import AsyncSessionLocal, apply_rls_context
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
    def __init__(
        self,
        session_or_factory: AsyncSession | async_sessionmaker[AsyncSession] | None = None,
        *,
        rls_enforced: bool = False,
    ):
        self._target = AsyncSessionLocal if session_or_factory is None else session_or_factory
        self._rls_enforced = rls_enforced

    async def _run_in_session(self, user_id: UUID, action: Callable[[AsyncSession], Any]) -> Any:
        if isinstance(self._target, AsyncSession):
            return await action(self._target)
        async with self._target() as session:
            async with session.begin():
                if self._rls_enforced:
                    await apply_rls_context(session, user_id)
                return await action(session)

    async def consume(self, user_id: UUID, day: date, feature: str) -> int:
        now = datetime.now(timezone.utc)

        async def _action(session: AsyncSession) -> int:
            await session.execute(
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
                await session.execute(
                    select(func.coalesce(func.sum(LlmUsageORM.calls), 0)).where(
                        LlmUsageORM.user_id == user_id, LlmUsageORM.usage_date == day
                    )
                )
            ).scalar_one()
            return int(total)

        return await self._run_in_session(user_id, _action)

    async def release(self, user_id: UUID, day: date, feature: str) -> None:
        async def _action(session: AsyncSession) -> None:
            await session.execute(
                update(LlmUsageORM)
                .where(
                    LlmUsageORM.user_id == user_id,
                    LlmUsageORM.usage_date == day,
                    LlmUsageORM.feature == feature,
                )
                .values(calls=func.greatest(LlmUsageORM.calls - 1, 0))
            )

        await self._run_in_session(user_id, _action)

    async def add_tokens(self, user_id: UUID, day: date, feature: str, tokens: int) -> None:
        async def _action(session: AsyncSession) -> None:
            await session.execute(
                update(LlmUsageORM)
                .where(
                    LlmUsageORM.user_id == user_id,
                    LlmUsageORM.usage_date == day,
                    LlmUsageORM.feature == feature,
                )
                .values(tokens=LlmUsageORM.tokens + tokens)
            )

        await self._run_in_session(user_id, _action)
