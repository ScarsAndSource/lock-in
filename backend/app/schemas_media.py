from __future__ import annotations

from datetime import time
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas_chat import SupportOut


class CheckinParseRequest(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=2000)]


class ParsedHabitOut(BaseModel):
    habit_id: UUID
    status: Literal["done", "partial", "skipped", "floor", "stretch"]


class ParsedSleepOut(BaseModel):
    time_to_bed: time | None
    time_woke: time | None
    self_rated_quality: int | None


class ParsedMoodOut(BaseModel):
    valence: int
    energy: int


class CheckinProposalOut(BaseModel):
    """A PROPOSAL. Nothing is saved until the person confirms through POST /checkins/{date}/confirm."""
    transcript: str | None
    habits: list[ParsedHabitOut]
    sleep: ParsedSleepOut | None
    screen_time_minutes: int | None
    mood: ParsedMoodOut | None
    journal: str | None
    empty: bool
    support: SupportOut | None = None


class ScreenshotProposalOut(BaseModel):
    total_minutes: int
    category_breakdown: dict[str, int]
    confidence: Literal["high", "medium", "low"]
    source: Literal["screenshot"] = "screenshot"
