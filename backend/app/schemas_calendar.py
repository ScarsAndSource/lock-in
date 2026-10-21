from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.services.calendar_import import MAX_ICS_CHARS


class ImportIn(BaseModel):
    ics: str = Field(min_length=1, max_length=MAX_ICS_CHARS)
    source: str | None = Field(default=None, max_length=40)


class ImportOut(BaseModel):
    source: str
    added: int
    exams: int
    skipped: int
    warnings: list[str]


class EventOut(BaseModel):
    id: str
    title: str
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    kind: Literal["exam", "class", "other"]
    kind_locked: bool
    source: str


class KindIn(BaseModel):
    kind: Literal["exam", "class", "other"]


class ExamOut(BaseModel):
    id: str
    title: str
    starts_at: datetime
    all_day: bool
    day: date
    days_until: int


class SourceOut(BaseModel):
    source: str
    events: int
    exams: int
    last_imported_at: datetime
