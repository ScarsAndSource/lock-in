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


_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class ProposedItemOut(BaseModel):
    """One thing read off a photo. `type` event goes on the calendar, `task` becomes a task. Nothing is saved yet."""
    type: Literal["event", "task"]
    title: str
    date: date | None
    start: str | None = Field(default=None, pattern=_HHMM)
    end: str | None = Field(default=None, pattern=_HHMM)
    kind: Literal["exam", "class", "other"] | None = None


class ScheduleProposalOut(BaseModel):
    items: list[ProposedItemOut]
    skipped: int          # undated or unreadable entries (a weekly timetable has no dates): add those by hand or via .ics


class PhotoEventIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    date: date
    start: str | None = Field(default=None, pattern=_HHMM)
    end: str | None = Field(default=None, pattern=_HHMM)
    kind: Literal["exam", "class", "other"] = "other"


class PhotoEventsIn(BaseModel):
    events: list[PhotoEventIn] = Field(min_length=1, max_length=60)


class PhotoEventsOut(BaseModel):
    added: int
    duplicates: int


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
