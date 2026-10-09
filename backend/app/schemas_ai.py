"""
Pydantic schemas for AI-generated content (insights, retros).
Stub for slice 8 — the full insights slice is later.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class InsightOut(BaseModel):
    id: UUID
    generated_on: date
    generated_at: datetime
    pattern_key: str
    insight_text: str
    next_step: str
    source_domains: list[str]
    narrated: bool
    user_feedback: str | None = None


class RefreshOut(BaseModel):
    generated: list[InsightOut]
    skipped_reason: str | None = None


class InsightFeedbackRequest(BaseModel):
    feedback: Literal["accurate", "not_quite", "unsure"]
