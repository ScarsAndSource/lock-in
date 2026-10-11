from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel


class PauseCreateRequest(BaseModel):
    start_date: date
    end_date: date
    habit_id: UUID | None = None  # omitted = pause everything


class PauseOut(BaseModel):
    id: UUID
    start_date: date
    end_date: date
    active: bool
    habit_id: UUID | None = None


class PausedHabitOut(BaseModel):
    habit_id: UUID
    name: str
    until: date
