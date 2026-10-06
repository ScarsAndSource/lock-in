from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas_ai import InsightOut, RefreshOut


class RetroGenerateRequest(BaseModel):
    week_start: date | None = None   # a Monday; omitted = the most recent completed week


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


class RetroDetailOut(RetroOut):
    status: Literal["ready", "completed"]
    pending_ratings: list[InsightOut]


class RetroCompleteOut(BaseModel):
    retro: RetroOut
    insights: RefreshOut
