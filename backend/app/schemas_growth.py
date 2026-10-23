from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AutopsyOut(BaseModel):
    id: UUID
    habit_id: UUID
    habit_name: str
    consistency_pct: float
    window_days: int
    floor_text: str | None
    current_label: str
    lighter_label: str | None
    identity_sentence: str | None
    identity_confidence: int | None


class PromptOut(BaseModel):
    autopsy: AutopsyOut | None
    identity_due: bool


class IdentityOut(BaseModel):
    sentence: str
    matters: str
    why_now: str
    importance: int
    confidence: int
    votes: int
    updated_at: datetime


class IdentityPutRequest(BaseModel):
    matters: str = Field(max_length=1000)
    why_now: str = Field(max_length=1000)
    importance: int = Field(ge=0, le=10)
    confidence: int = Field(ge=0, le=10)
    sentence: str = Field(max_length=1000)


class JournalEntryOut(BaseModel):
    entry_date: date
    text: str
    sticker: str | None


class JournalPutRequest(BaseModel):
    text: str = Field(default="", max_length=10_000)
    sticker: str | None = Field(default=None, max_length=8)


class JournalPutOut(BaseModel):
    entry: JournalEntryOut
    support: dict[str, Any] | None = None


class AutopsyApplyRequest(BaseModel):
    reason: str = Field(max_length=32)
    floor_text: str | None = Field(default=None, max_length=1000)
    cue: str | None = Field(default=None, max_length=1000)
    choice: str | None = Field(default=None, max_length=16)


class MessageOut(BaseModel):
    message: str


class FutureCreateRequest(BaseModel):
    text: str | None = Field(default=None, max_length=1000)
    audio_b64: str | None = Field(default=None, max_length=800_000)
    audio_mime: str | None = Field(default=None, max_length=64)
    duration_s: int | None = Field(default=None, ge=1, le=60)
    send_at: str | None = Field(default=None, max_length=8)


class FuturePatchRequest(BaseModel):
    active: bool


class FutureOut(BaseModel):
    id: UUID
    text: str | None
    has_audio: bool
    duration_s: int | None
    send_at: str | None
    active: bool
    audio_b64: str | None = None
    audio_mime: str | None = None
