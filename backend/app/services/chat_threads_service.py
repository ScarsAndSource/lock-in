"""
Stored chat threads.
The thread layer wraps ChatService; everything the model sees is still built by ChatService
(facts + isolated question).

What this layer adds:
- the history window is loaded SERVER-SIDE from storage, so a client can't drop earlier turns
  to slip past the crisis latch (ChatService screens the last user turns it is given)
- free text (title, messages, next steps) is encrypted at rest; meta holds no free text
- a thread's title never echoes crisis text ("Conversation" instead)
- threads inactive for `retention_days` are pruned lazily (0 disables)
- nothing is stored unless the reply succeeded (a 429 / validation error leaves no orphan thread)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID, uuid4

from app.dates import Clock, utc_now
from app.domain import ChatMessage, ChatThread
from app.exceptions import NotFoundError, ValidationError
from app.repositories.chat_thread_repository import ChatThreadRepository
from app.safety import is_crisis, support_payload
from app.security import FieldEncryptor
from app.services.chat_service import ChatService
from app.services.narration import sanitize_user_text
from app.services.profile_service import ProfileService

logger = logging.getLogger("lockin.chat.threads")

MAX_THREADS = 100
MAX_MESSAGES_PER_THREAD = 200
HISTORY_WINDOW = 6  # same window ChatService reads
MAX_TITLE_LEN = 80
DEFAULT_TITLE = "New conversation"
SENSITIVE_TITLE = "Conversation"
UNREADABLE = "[message unavailable]"


@dataclass(slots=True)
class ThreadView:
    thread: ChatThread
    title: str
    message_count: int


@dataclass(slots=True)
class MessageView:
    message: ChatMessage
    content: str
    next_step: str | None
    mode: str | None
    cited_days: list[str] = field(default_factory=list)
    narrated: bool = False
    model: str | None = None
    actions: list = field(default_factory=list)   # live reply only: pending/undo payloads are not persisted


@dataclass(slots=True)
class SendResult:
    thread: ThreadView
    user_message: MessageView
    reply: MessageView
    support: dict | None


@dataclass(slots=True)
class ThreadDetail:
    thread: ThreadView
    messages: list[MessageView]
    has_more: bool
    support: dict | None


def clean_title(raw: str) -> str:
    title = sanitize_user_text(raw, MAX_TITLE_LEN, single_line=True)
    if not title:
        raise ValidationError("Title can't be blank.")
    return title


class ChatThreadsService:
    def __init__(
        self,
        repo: ChatThreadRepository,
        chat: ChatService,
        encryptor: FieldEncryptor,
        profiles: ProfileService,
        retention_days: int = 90,
        clock: Clock = utc_now,
    ):
        self._repo, self._chat, self._enc = repo, chat, encryptor
        self._profiles, self._retention_days, self._clock = profiles, retention_days, clock

    # ---------------------------------------------------------------- helpers
    def _encrypt(self, text: str | None) -> bytes | None:
        return self._enc.encrypt(text) if text else None

    def _decrypt(self, blob: bytes | None) -> str | None:
        try:
            return self._enc.decrypt(blob) if blob else None
        except ValueError:
            logger.warning("chat: an undecryptable value was skipped")
            return None

    def _thread_view(self, thread: ChatThread, count: int) -> ThreadView:
        return ThreadView(thread, self._decrypt(thread.title_encrypted) or DEFAULT_TITLE, count)

    def _message_view(self, m: ChatMessage) -> MessageView:
        meta = m.meta or {}
        return MessageView(
            message=m,
            content=self._decrypt(m.content_encrypted) or UNREADABLE,
            next_step=self._decrypt(m.next_step_encrypted),
            mode=meta.get("mode"),
            cited_days=list(meta.get("cited_days") or []),
            narrated=bool(meta.get("narrated", False)),
            model=meta.get("model"),
        )

    async def _prune(self, user_id: UUID) -> None:
        if self._retention_days > 0:
            await self._repo.delete_inactive_since(user_id, self._clock() - timedelta(days=self._retention_days))

    async def _require(self, user_id: UUID, thread_id: UUID) -> ChatThread:
        thread = await self._repo.get_thread(user_id, thread_id)
        if thread is None:
            raise NotFoundError("No conversation found for this user.")
        return thread

    # ---------------------------------------------------------------- send
    async def send(
        self,
        user_id: UUID,
        message: str,
        thread_id: UUID | None = None,
        before_model: Callable[[], None] | None = None,
    ) -> SendResult:
        text = message.strip()
        if not text:
            raise ValidationError("Message can't be blank.")

        thread: ChatThread | None = None
        history: list[tuple[str, str]] = []
        if thread_id is not None:
            thread = await self._require(user_id, thread_id)
            if await self._repo.count_messages(user_id, thread.id) >= MAX_MESSAGES_PER_THREAD:
                raise ValidationError("This conversation is full. Start a new one.")
            for m in await self._repo.list_messages(user_id, thread.id, HISTORY_WINDOW, None):
                content = self._decrypt(m.content_encrypted)
                if content:
                    history.append((m.role, content))
        else:
            await self._prune(user_id)
            if await self._repo.count_threads(user_id) >= MAX_THREADS:
                raise ValidationError("Too many conversations. Delete one you don't need.")

        reply = await self._chat.reply(user_id, text, history, before_model=before_model)
        # Only now do we write anything: a 429 / validation error above leaves no trace.

        now = self._clock()
        if thread is None:
            sensitive = reply.mode == "support" or is_crisis(text)
            title = SENSITIVE_TITLE if sensitive else (
                sanitize_user_text(text, 60, single_line=True) or DEFAULT_TITLE
            )
            thread = await self._repo.create_thread(ChatThread(
                id=uuid4(),
                user_id=user_id,
                created_at=now,
                last_message_at=now,
                title_encrypted=self._encrypt(title),
            ))

        user_msg = await self._repo.add_message(ChatMessage(
            id=uuid4(),
            thread_id=thread.id,
            user_id=user_id,
            role="user",
            content_encrypted=self._encrypt(text),
            created_at=now,
        ))
        bot_msg = await self._repo.add_message(ChatMessage(
            id=uuid4(),
            thread_id=thread.id,
            user_id=user_id,
            role="assistant",
            content_encrypted=self._encrypt(reply.reply),
            next_step_encrypted=self._encrypt(reply.next_step),
            meta={
                "mode": reply.mode,
                "cited_days": reply.cited_days,
                "narrated": reply.narrated,
                "model": reply.model,
                # structure only, never free text (summaries live in the encrypted content)
                **({"actions": [{"tool": c.tool, "status": c.status} for c in reply.actions]} if reply.actions else {}),
            },
            created_at=now + timedelta(milliseconds=1),
        ))

        count = await self._repo.count_messages(user_id, thread.id)
        bot_view = self._message_view(bot_msg)
        bot_view.actions = list(reply.actions)
        return SendResult(
            thread=self._thread_view(thread, count),
            user_message=self._message_view(user_msg),
            reply=bot_view,
            support=reply.support,
        )

    # ---------------------------------------------------------------- read / manage
    async def list_threads(self, user_id: UUID, limit: int = 50) -> list[ThreadView]:
        await self._prune(user_id)
        return [self._thread_view(t, n) for t, n in await self._repo.list_threads(user_id, limit)]

    async def get_thread(
        self,
        user_id: UUID,
        thread_id: UUID,
        limit: int = 50,
        before: datetime | None = None,
    ) -> ThreadDetail:
        thread = await self._require(user_id, thread_id)
        rows = await self._repo.list_messages(user_id, thread.id, limit + 1, before)
        has_more = len(rows) > limit
        if has_more:
            rows = rows[len(rows) - limit:]  # drop the OLDEST extra row
        views = [self._message_view(m) for m in rows]
        support = None
        if any(v.mode == "support" for v in views):
            support = support_payload((await self._profiles.get(user_id)).timezone)
        count = await self._repo.count_messages(user_id, thread.id)
        return ThreadDetail(self._thread_view(thread, count), views, has_more, support)

    async def rename(self, user_id: UUID, thread_id: UUID, title: str) -> ThreadView:
        thread = await self._require(user_id, thread_id)
        await self._repo.set_title(user_id, thread_id, self._encrypt(clean_title(title)))
        thread.title_encrypted = self._encrypt(clean_title(title))
        return self._thread_view(thread, await self._repo.count_messages(user_id, thread_id))

    async def delete(self, user_id: UUID, thread_id: UUID) -> None:
        if not await self._repo.delete_thread(user_id, thread_id):
            raise NotFoundError("No conversation found for this user.")

    async def delete_all(self, user_id: UUID) -> int:
        return await self._repo.delete_all(user_id)
