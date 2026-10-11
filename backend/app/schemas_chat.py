from __future__ import annotations

from typing import Literal

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


class ChatOut(BaseModel):
    mode: Literal["answer", "support", "no_data", "fallback"]
    reply: str
    next_step: str | None = None
    cited_days: list[str] = Field(default_factory=list)
    narrated: bool = False
    model: str | None = None
    support: SupportOut | None = None
