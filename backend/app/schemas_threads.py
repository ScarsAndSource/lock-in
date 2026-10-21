from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas_chat import ActionCardOut, SupportOut


class ThreadOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    last_message_at: datetime
    message_count: int


class MessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    next_step: str | None = None
    mode: Literal["answer", "support", "no_data", "fallback", "action"] | None = None  # assistant messages only
    cited_days: list[str] = Field(default_factory=list)
    narrated: bool = False
    model: str | None = None
    actions: list[ActionCardOut] = Field(default_factory=list)  # only on the live reply that did something
    created_at: datetime


class ThreadDetailOut(BaseModel):
    thread: ThreadOut
    messages: list[MessageOut]
    has_more: bool
    support: SupportOut | None = None


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    thread_id: UUID | None = None  # omitted = start a new conversation


class SendMessageOut(BaseModel):
    thread: ThreadOut
    user_message: MessageOut
    reply: MessageOut
    support: SupportOut | None = None


class RenameThreadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class DeletedOut(BaseModel):
    deleted: int
