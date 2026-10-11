from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas_friction import PauseOut

PresetKey = Literal["today", "3_days", "this_week", "1_week", "2_weeks"]


class PauseShortcutOut(BaseModel):
    key: PresetKey
    label: str
    start_date: date
    end_date: date
    days: int


class HabitPauseRowOut(BaseModel):
    habit_id: UUID
    name: str
    state: Literal["active", "paused", "upcoming"]
    effective_paused: bool
    paused_by: Literal["habit", "all"] | None
    pause: PauseOut | None


class PauseOverviewOut(BaseModel):
    today: date
    global_pause: PauseOut | None
    habits: list[HabitPauseRowOut]


class QuickPauseRequest(BaseModel):
    preset: PresetKey
    habit_id: UUID | None = None  # omitted = pause everything


class ResumeRequest(BaseModel):
    habit_id: UUID | None = None  # omitted = resume the global pause


class ResumeOut(BaseModel):
    resumed: int
    still_paused_by_all: bool
