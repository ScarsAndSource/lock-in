from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NextTargetOut(BaseModel):
    type: Literal["habit", "task", "checkin", "urge", "none"]
    habit_id: str | None = None
    status: Literal["done", "floor"] | None = None
    task_id: str | None = None


class NextActionOut(BaseModel):
    key: str
    kind: Literal["floor", "deadline", "guard", "close", "habit", "task", "checkin", "clear"]
    eyebrow: str
    title: str
    detail: str | None = None
    cta: str | None = None
    target: NextTargetOut
    why: str | None = None
    voice: str | None = None


class RiskWindowOut(BaseModel):
    start: int
    end: int
    weight: float


class RhythmOut(BaseModel):
    wake: int | None = None
    bed: int | None = None
    checkin: int | None = None
    first_open: int | None = None
    windows: list[RiskWindowOut]
    samples: int
    confidence: Literal["low", "medium", "high"]


class CompanionNowOut(BaseModel):
    next_action: NextActionOut
    rhythm: RhythmOut
    local_minute: int
    tone: Literal["direct", "coach"]
    habits_done: int
    habits_total: int
    confirmed: bool


class EventIn(BaseModel):
    kind: Literal["app_open", "nba_shown", "nba_acted", "nba_skipped", "push_opened"]
    ref: str | None = Field(default=None, max_length=80)
