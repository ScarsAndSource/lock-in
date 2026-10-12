from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Task
from app.models import TaskORM

_FIELDS = (
    "title", "notes", "importance", "status", "due_at", "due_has_time", "remind_at", "repeat_days",
    "snoozed_until", "nudge_count", "last_nudged_at", "last_done_at", "done_count", "completed_at",
)


class TaskRepository(Protocol):
    async def create(self, task: Task) -> Task: ...
    async def get(self, user_id: UUID, task_id: UUID) -> Task | None: ...
    async def list(self, user_id: UUID, status: str | None = None, limit: int = 500) -> list[Task]: ...
    async def count_open(self, user_id: UUID) -> int: ...
    async def save(self, task: Task, now: datetime) -> Task | None: ...
    async def delete(self, user_id: UUID, task_id: UUID) -> bool: ...


def _task(row: TaskORM) -> Task:
    return Task(
        id=row.id, user_id=row.user_id, title=row.title, created_at=row.created_at, notes=row.notes,
        source_text=row.source_text, importance=row.importance, status=row.status, due_at=row.due_at,
        due_has_time=row.due_has_time, remind_at=row.remind_at, repeat_days=row.repeat_days,
        snoozed_until=row.snoozed_until, nudge_count=row.nudge_count, last_nudged_at=row.last_nudged_at,
        last_done_at=row.last_done_at, done_count=row.done_count, completed_at=row.completed_at,
        ai_parsed=row.ai_parsed,
    )


class SqlAlchemyTaskRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, task: Task) -> Task:
        self._session.add(TaskORM(
            id=task.id, user_id=task.user_id, title=task.title, notes=task.notes, source_text=task.source_text,
            importance=task.importance, status=task.status, due_at=task.due_at, due_has_time=task.due_has_time,
            remind_at=task.remind_at, repeat_days=task.repeat_days, snoozed_until=task.snoozed_until,
            nudge_count=task.nudge_count, last_nudged_at=task.last_nudged_at, last_done_at=task.last_done_at,
            done_count=task.done_count, completed_at=task.completed_at, ai_parsed=task.ai_parsed,
            created_at=task.created_at, updated_at=task.created_at,
        ))
        await self._session.flush()
        return task

    async def get(self, user_id: UUID, task_id: UUID) -> Task | None:
        stmt = select(TaskORM).where(TaskORM.id == task_id, TaskORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _task(row) if row else None

    async def list(self, user_id: UUID, status: str | None = None, limit: int = 500) -> list[Task]:
        stmt = select(TaskORM).where(TaskORM.user_id == user_id)
        if status is not None:
            stmt = stmt.where(TaskORM.status == status)
        stmt = stmt.order_by(TaskORM.created_at.desc()).limit(limit)
        return [_task(r) for r in (await self._session.execute(stmt)).scalars().all()]

    async def count_open(self, user_id: UUID) -> int:
        stmt = select(func.count()).select_from(TaskORM).where(TaskORM.user_id == user_id, TaskORM.status == "open")
        return int((await self._session.execute(stmt)).scalar_one())

    async def save(self, task: Task, now: datetime) -> Task | None:
        stmt = select(TaskORM).where(TaskORM.id == task.id, TaskORM.user_id == task.user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        for name in _FIELDS:
            setattr(row, name, getattr(task, name))
        row.updated_at = now
        await self._session.flush()
        return _task(row)

    async def delete(self, user_id: UUID, task_id: UUID) -> bool:
        result = await self._session.execute(
            delete(TaskORM).where(TaskORM.id == task_id, TaskORM.user_id == user_id)
        )
        return (result.rowcount or 0) > 0
