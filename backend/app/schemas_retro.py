from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas_ai import InsightOut, RefreshOut


class RetroGenerateRequest(BaseModel):
    week_start: date | None = None   # a Monday; omitted = the most recent completed week
    mode: Literal["auto", "rough", "normal"] = "auto"


class RetroToneRequest(BaseModel):
    mode: Literal["auto", "rough", "normal"]


class WeekModeOut(BaseModel):
    mode: Literal["normal", "rough"]
    reasons: list[str]
    source: Literal["auto", "user"]


class RetroOut(BaseModel):
    id: UUID
    week_start: date
    week_end: date
    generated_at: datetime
    narrative: str
    next_step: str
    summary: dict
    evidence_refs: dict
    narrated: bool
    completed_at: datetime | None
    week_mode: WeekModeOut | None = None  # None for retros generated before this feature


class RetroDetailOut(RetroOut):
    status: Literal["ready", "completed"]
    pending_ratings: list[InsightOut]


class RetroCompleteOut(BaseModel):
    retro: RetroOut
    insights: RefreshOut

