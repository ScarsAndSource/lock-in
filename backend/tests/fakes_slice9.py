from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.domain import ChatMessage, ChatThread


class InMemoryChatThreadRepository:

    def __init__(self):
        self.threads: dict[UUID, ChatThread] = {}
        self.messages: dict[UUID, ChatMessage] = {}

    async def create_thread(self, thread):
        self.threads[thread.id] = thread
        return thread

    async def get_thread(self, user_id, thread_id):
        t = self.threads.get(thread_id)
        return t if t is not None and t.user_id == user_id else None

    async def _count(self, thread_id) -> int:
        return sum(1 for m in self.messages.values() if m.thread_id == thread_id)

    async def list_threads(self, user_id, limit):
        rows = sorted(
            (t for t in self.threads.values() if t.user_id == user_id),
            key=lambda t: t.last_message_at,
            reverse=True,
        )
        return [(t, await self._count(t.id)) for t in rows[:limit]]

    async def count_threads(self, user_id):
        return sum(1 for t in self.threads.values() if t.user_id == user_id)

    async def set_title(self, user_id, thread_id, title_encrypted):
        t = await self.get_thread(user_id, thread_id)
        if t is None:
            return False
        t.title_encrypted = title_encrypted
        return True

    def _drop(self, thread_id) -> None:
        self.threads.pop(thread_id, None)
        for mid in [i for i, m in self.messages.items() if m.thread_id == thread_id]:
            del self.messages[mid]

    async def delete_thread(self, user_id, thread_id):
        if await self.get_thread(user_id, thread_id) is None:
            return False
        self._drop(thread_id)
        return True

    async def delete_all(self, user_id):
        ids = [i for i, t in self.threads.items() if t.user_id == user_id]
        for i in ids:
            self._drop(i)
        return len(ids)

    async def delete_inactive_since(self, user_id, cutoff: datetime):
        ids = [i for i, t in self.threads.items() if t.user_id == user_id and t.last_message_at < cutoff]
        for i in ids:
            self._drop(i)
        return len(ids)

    async def add_message(self, message):
        self.messages[message.id] = message
        t = self.threads.get(message.thread_id)
        if t is not None:
            t.last_message_at = message.created_at
        return message

    async def count_messages(self, user_id, thread_id):
        return sum(1 for m in self.messages.values() if m.thread_id == thread_id and m.user_id == user_id)

    async def list_messages(self, user_id, thread_id, limit, before):
        rows = [
            m for m in self.messages.values()
            if m.thread_id == thread_id and m.user_id == user_id and (before is None or m.created_at < before)
        ]
        rows.sort(key=lambda m: m.created_at)
        return rows[-limit:]
