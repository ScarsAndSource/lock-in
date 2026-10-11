from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import ChatMessage, ChatThread
from app.models import ChatMessageORM, ChatThreadORM


class ChatThreadRepository(Protocol):
    async def create_thread(self, thread: ChatThread) -> ChatThread: ...
    async def get_thread(self, user_id: UUID, thread_id: UUID) -> ChatThread | None: ...
    async def list_threads(self, user_id: UUID, limit: int) -> list[tuple[ChatThread, int]]: ...
    async def count_threads(self, user_id: UUID) -> int: ...
    async def set_title(self, user_id: UUID, thread_id: UUID, title_encrypted: bytes) -> bool: ...
    async def delete_thread(self, user_id: UUID, thread_id: UUID) -> bool: ...
    async def delete_all(self, user_id: UUID) -> int: ...
    async def delete_inactive_since(self, user_id: UUID, cutoff: datetime) -> int: ...
    async def add_message(self, message: ChatMessage) -> ChatMessage: ...
    async def count_messages(self, user_id: UUID, thread_id: UUID) -> int: ...
    async def list_messages(
        self, user_id: UUID, thread_id: UUID, limit: int, before: datetime | None
    ) -> list[ChatMessage]:
        """Newest `limit` messages strictly before `before`, returned oldest-first."""
        ...


def _thread(row: ChatThreadORM) -> ChatThread:
    return ChatThread(
        id=row.id,
        user_id=row.user_id,
        created_at=row.created_at,
        last_message_at=row.last_message_at,
        title_encrypted=row.title_encrypted,
    )


def _message(row: ChatMessageORM) -> ChatMessage:
    return ChatMessage(
        id=row.id,
        thread_id=row.thread_id,
        user_id=row.user_id,
        role=row.role,
        content_encrypted=row.content_encrypted,
        created_at=row.created_at,
        next_step_encrypted=row.next_step_encrypted,
        meta=row.meta or {},
    )


class SqlAlchemyChatThreadRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_thread(self, thread: ChatThread) -> ChatThread:
        self._session.add(ChatThreadORM(
            id=thread.id,
            user_id=thread.user_id,
            title_encrypted=thread.title_encrypted,
            last_message_at=thread.last_message_at,
            created_at=thread.created_at,
            updated_at=thread.created_at,
        ))
        await self._session.flush()
        return thread

    async def get_thread(self, user_id: UUID, thread_id: UUID) -> ChatThread | None:
        stmt = select(ChatThreadORM).where(ChatThreadORM.id == thread_id, ChatThreadORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _thread(row) if row else None

    async def list_threads(self, user_id: UUID, limit: int) -> list[tuple[ChatThread, int]]:
        stmt = (
            select(ChatThreadORM, func.count(ChatMessageORM.id))
            .outerjoin(ChatMessageORM, ChatMessageORM.thread_id == ChatThreadORM.id)
            .where(ChatThreadORM.user_id == user_id)
            .group_by(ChatThreadORM.id)
            .order_by(ChatThreadORM.last_message_at.desc())
            .limit(limit)
        )
        return [(_thread(t), int(n)) for t, n in (await self._session.execute(stmt)).all()]

    async def count_threads(self, user_id: UUID) -> int:
        stmt = select(func.count()).select_from(ChatThreadORM).where(ChatThreadORM.user_id == user_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def set_title(self, user_id: UUID, thread_id: UUID, title_encrypted: bytes) -> bool:
        result = await self._session.execute(
            update(ChatThreadORM)
            .where(ChatThreadORM.id == thread_id, ChatThreadORM.user_id == user_id)
            .values(title_encrypted=title_encrypted, updated_at=datetime.now(timezone.utc))
        )
        return (result.rowcount or 0) > 0

    async def delete_thread(self, user_id: UUID, thread_id: UUID) -> bool:
        result = await self._session.execute(
            delete(ChatThreadORM).where(ChatThreadORM.id == thread_id, ChatThreadORM.user_id == user_id)
        )
        return (result.rowcount or 0) > 0

    async def delete_all(self, user_id: UUID) -> int:
        result = await self._session.execute(delete(ChatThreadORM).where(ChatThreadORM.user_id == user_id))
        return result.rowcount or 0

    async def delete_inactive_since(self, user_id: UUID, cutoff: datetime) -> int:
        result = await self._session.execute(
            delete(ChatThreadORM).where(ChatThreadORM.user_id == user_id, ChatThreadORM.last_message_at < cutoff)
        )
        return result.rowcount or 0

    async def add_message(self, message: ChatMessage) -> ChatMessage:
        self._session.add(ChatMessageORM(
            id=message.id,
            user_id=message.user_id,
            thread_id=message.thread_id,
            role=message.role,
            content_encrypted=message.content_encrypted,
            next_step_encrypted=message.next_step_encrypted,
            meta=message.meta,
            created_at=message.created_at,
        ))
        await self._session.execute(
            update(ChatThreadORM)
            .where(ChatThreadORM.id == message.thread_id, ChatThreadORM.user_id == message.user_id)
            .values(last_message_at=message.created_at, updated_at=datetime.now(timezone.utc))
        )
        await self._session.flush()
        return message

    async def count_messages(self, user_id: UUID, thread_id: UUID) -> int:
        stmt = select(func.count()).select_from(ChatMessageORM).where(
            ChatMessageORM.user_id == user_id, ChatMessageORM.thread_id == thread_id
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_messages(
        self, user_id: UUID, thread_id: UUID, limit: int, before: datetime | None
    ) -> list[ChatMessage]:
        stmt = select(ChatMessageORM).where(
            ChatMessageORM.user_id == user_id, ChatMessageORM.thread_id == thread_id
        )
        if before is not None:
            stmt = stmt.where(ChatMessageORM.created_at < before)
        rows = (await self._session.execute(stmt.order_by(ChatMessageORM.created_at.desc()).limit(limit))).scalars().all()
        return [_message(r) for r in reversed(rows)]
