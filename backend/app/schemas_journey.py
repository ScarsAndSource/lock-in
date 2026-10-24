from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class SeasonStartRequest(BaseModel):
    name: str | None = Field(None, max_length=60)
    focus_habit_ids: list[UUID] = Field(default_factory=list, max_length=3)


class FocusRequest(BaseModel):
    focus_habit_ids: list[UUID] = Field(default_factory=list, max_length=50)


class RecallCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    topics: str = Field(min_length=1, max_length=2000)
    exam_date: date | None = None


class RecallDoneRequest(BaseModel):
    extra_topics: str | None = Field(None, max_length=1000)


class SnapshotRequest(BaseModel):
    wellbeing: int = Field(ge=0, le=10)
    sleep: int = Field(ge=0, le=10)
    focus: int = Field(ge=0, le=10)
    becoming: int = Field(ge=0, le=10)
    automatic: int = Field(ge=0, le=10)
    custom_label: str | None = Field(None, max_length=40)
    custom_value: float | None = Field(None, ge=-1_000_000_000, le=1_000_000_000)


class CheckRequest(BaseModel):
    holding: bool
    