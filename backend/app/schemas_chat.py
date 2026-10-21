from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)


class SupportResourceOut(BaseModel):
    name: str
    contact: str
    detail: str


class SupportOut(BaseModel):
    region: str
    message: str
    resources: list[SupportResourceOut]
    verified_on: str


class ActionCardOut(BaseModel):
    """What the agent did (applied + undo payload) or wants to do (pending + args to confirm). Live replies only."""
    id: str
    tool: str
    status: Literal["applied", "pending", "failed"]
    summary: str
    reason: str | None = None
    args: dict[str, Any] | None = None
    undo: dict[str, Any] | None = None


class ConfirmActionRequest(BaseModel):
    tool: str = Field(min_length=1, max_length=40)
    args: dict[str, Any]


class UndoActionRequest(BaseModel):
    undo: dict[str, Any]


class UndoOut(BaseModel):
    message: str


class ChatOut(BaseModel):
    mode: Literal["answer", "support", "no_data", "fallback", "action"]
    reply: str
    next_step: str | None = None
    cited_days: list[str] = Field(default_factory=list)
    narrated: bool = False
    model: str | None = None
    support: SupportOut | None = None
