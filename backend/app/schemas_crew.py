from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class UsernameIn(BaseModel):
    username: str = Field(min_length=1, max_length=40)


class ShareIn(BaseModel):
    days: bool = False
    hours: bool = False
    proud: bool = False
    focus: bool = False
    habits: bool = False


class CrewCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class RespondIn(BaseModel):
    accept: bool


class JoinIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class CodeIn(BaseModel):
    revoke: bool = False


class QuietIn(BaseModel):
    quiet: bool


class CloseWeekIn(BaseModel):
    proud: str | None = Field(default=None, max_length=300)
    focus: str | None = Field(default=None, max_length=300)
    habits: list[str] = Field(default_factory=list, max_length=5)


class CheerIn(BaseModel):
    to: str = Field(min_length=1, max_length=40)
    kind: str = Field(min_length=1, max_length=20)


class BoostIn(BaseModel):
    to: str | None = Field(default=None, max_length=40)  # None = the whole crew


class GoalIn(BaseModel):
    hours: int | None = Field(default=None, ge=1, le=200)   # None clears next week's goal


class BuddyIn(BaseModel):
    crew_id: UUID
    to: str = Field(min_length=1, max_length=40)
    threshold: int = Field(default=3, ge=2, le=7)
    message: str = Field(min_length=1, max_length=300)
    auto_send: bool = False


class DuelIn(BaseModel):
    crew_id: UUID
    to: str = Field(min_length=1, max_length=40)
