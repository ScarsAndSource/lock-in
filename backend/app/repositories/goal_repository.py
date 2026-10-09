from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Goal, GoalStatus, Intention
from app.models import GoalORM, IntentionORM


class GoalRepository(Protocol):
    async def create(self, goal: Goal) -> Goal: ...
    async def get(self, user_id: UUID, goal_id: UUID) -> Goal | None: ...
    async def list(self, user_id: UUID, status: GoalStatus | None = None) -> list[Goal]: ...
    async def list_active_by_domain(self, user_id: UUID, domain: str) -> list[Goal]: ...
    async def count_active(self, user_id: UUID) -> int: ...
    async def update(
        self, user_id: UUID, goal_id: UUID, definition: str | None, status: GoalStatus | None,
        target: dict | None, now: datetime,
    ) -> Goal | None: ...


class IntentionRepository(Protocol):
    async def create(self, intention: Intention) -> Intention: ...
    async def get(self, user_id: UUID, intention_id: UUID) -> Intention | None: ...
    async def list(self, user_id: UUID, domain: str | None = None, active_only: bool = False) -> list[Intention]: ...
    async def count_active(self, user_id: UUID) -> int: ...
    async def update(
        self, user_id: UUID, intention_id: UUID, cue: str | None, action: str | None,
        active: bool | None, now: datetime,
    ) -> Intention | None: ...
    async def delete(self, user_id: UUID, intention_id: UUID) -> bool: ...


def _goal(row: GoalORM) -> Goal:
    return Goal(
        id=row.id, user_id=row.user_id, domain=row.domain, definition=row.definition,
        target=row.target, status=GoalStatus(row.status), created_at=row.created_at,
    )


def _intention(row: IntentionORM) -> Intention:
    return Intention(
        id=row.id, user_id=row.user_id, linked_domain=row.linked_domain, cue=row.cue, action=row.action,
        created_at=row.created_at, linked_entity_id=row.linked_entity_id, active=row.active,
    )


class SqlAlchemyGoalRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, goal: Goal) -> Goal:
        self._session.add(GoalORM(
            id=goal.id, user_id=goal.user_id, domain=goal.domain, definition=goal.definition,
            target=goal.target, status=goal.status.value, created_at=goal.created_at, updated_at=goal.created_at,
        ))
        await self._session.flush()
        return goal

    async def get(self, user_id: UUID, goal_id: UUID) -> Goal | None:
        stmt = select(GoalORM).where(GoalORM.id == goal_id, GoalORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _goal(row) if row else None

    async def list(self, user_id: UUID, status: GoalStatus | None = None) -> list[Goal]:
        stmt = select(GoalORM).where(GoalORM.user_id == user_id)
        if status is not None:
            stmt = stmt.where(GoalORM.status == status.value)
        return [_goal(r) for r in (await self._session.execute(stmt.order_by(GoalORM.created_at))).scalars().all()]

    async def list_active_by_domain(self, user_id: UUID, domain: str) -> list[Goal]:
        stmt = select(GoalORM).where(
            GoalORM.user_id == user_id, GoalORM.domain == domain, GoalORM.status == "active"
        ).order_by(GoalORM.created_at.desc())
        return [_goal(r) for r in (await self._session.execute(stmt)).scalars().all()]

    async def count_active(self, user_id: UUID) -> int:
        stmt = select(func.count()).select_from(GoalORM).where(GoalORM.user_id == user_id, GoalORM.status == "active")
        return int((await self._session.execute(stmt)).scalar_one())

    async def update(
        self, user_id: UUID, goal_id: UUID, definition: str | None, status: GoalStatus | None,
        target: dict | None, now: datetime,
    ) -> Goal | None:
        stmt = select(GoalORM).where(GoalORM.id == goal_id, GoalORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        if definition is not None:
            row.definition = definition
        if status is not None:
            row.status = status.value
        if target is not None:
            row.target = target
        row.updated_at = now
        await self._session.flush()
        return _goal(row)


class SqlAlchemyIntentionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, intention: Intention) -> Intention:
        self._session.add(IntentionORM(
            id=intention.id, user_id=intention.user_id, linked_domain=intention.linked_domain,
            linked_entity_id=intention.linked_entity_id, cue=intention.cue, action=intention.action,
            active=intention.active, created_at=intention.created_at, updated_at=intention.created_at,
        ))
        await self._session.flush()
        return intention

    async def get(self, user_id: UUID, intention_id: UUID) -> Intention | None:
        stmt = select(IntentionORM).where(IntentionORM.id == intention_id, IntentionORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _intention(row) if row else None

    async def list(self, user_id: UUID, domain: str | None = None, active_only: bool = False) -> list[Intention]:
        stmt = select(IntentionORM).where(IntentionORM.user_id == user_id)
        if domain is not None:
            stmt = stmt.where(IntentionORM.linked_domain == domain)
        if active_only:
            stmt = stmt.where(IntentionORM.active.is_(True))
        rows = (await self._session.execute(stmt.order_by(IntentionORM.created_at))).scalars().all()
        return [_intention(r) for r in rows]

    async def count_active(self, user_id: UUID) -> int:
        stmt = select(func.count()).select_from(IntentionORM).where(
            IntentionORM.user_id == user_id, IntentionORM.active.is_(True)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def update(
        self, user_id: UUID, intention_id: UUID, cue: str | None, action: str | None,
        active: bool | None, now: datetime,
    ) -> Intention | None:
        stmt = select(IntentionORM).where(IntentionORM.id == intention_id, IntentionORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        if cue is not None:
            row.cue = cue
        if action is not None:
            row.action = action
        if active is not None:
            row.active = active
        row.updated_at = now
        await self._session.flush()
        return _intention(row)

    async def delete(self, user_id: UUID, intention_id: UUID) -> bool:
        result = await self._session.execute(
            delete(IntentionORM).where(IntentionORM.id == intention_id, IntentionORM.user_id == user_id)
        )
        return (result.rowcount or 0) > 0
