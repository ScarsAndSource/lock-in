from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.domain import HabitStatus


class WeekdaysFrequency(BaseModel):
    type: Literal["weekdays"]
    days: Annotated[list[int], Field(min_length=1, max_length=7)]

    @field_validator("days")
    @classmethod
    def _validate_day_range(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("days must each be 0 (Monday) through 6 (Sunday)")
        return v


class NPerWeekFrequency(BaseModel):
    type: Literal["n_per_week"]
    count: Annotated[int, Field(ge=1, le=7)]


TargetFrequencyIn = Annotated[
    WeekdaysFrequency | NPerWeekFrequency, Field(discriminator="type")
]


class HabitCreateRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    target_frequency: TargetFrequencyIn


class HabitOut(BaseModel):
    id: UUID
    name: str
    target_frequency: dict
    archived_at: datetime | None


class HabitLogRequest(BaseModel):
    log_date: date
    status: HabitStatus
    note: Annotated[str | None, Field(max_length=2000)] = None


class HabitLogOut(BaseModel):
    habit_id: UUID
    log_date: date
    status: HabitStatus
    note: str | None
    is_default: bool


class CheckinEntryOut(BaseModel):
    habit_id: UUID
    habit_name: str
    status: HabitStatus
    is_default: bool
    is_low_confidence: bool
    reason: str


class CheckinViewOut(BaseModel):
    checkin_date: date
    already_confirmed: bool
    entries: list[CheckinEntryOut]


class CheckinOverrideIn(BaseModel):
    habit_id: UUID
    status: HabitStatus
    note: Annotated[str | None, Field(max_length=2000)] = None


class CheckinConfirmRequest(BaseModel):
    overrides: list[CheckinOverrideIn] = Field(default_factory=list)
    journal_text: Annotated[str | None, Field(max_length=10_000)] = None

    @field_validator("overrides")
    @classmethod
    def _no_duplicate_habit_overrides(cls, v: list[CheckinOverrideIn]) -> list[CheckinOverrideIn]:
        habit_ids = [o.habit_id for o in v]
        if len(habit_ids) != len(set(habit_ids)):
            raise ValueError("overrides must not reference the same habit_id more than once")
        return v


class CheckinConfirmOut(BaseModel):
    checkin_date: date
    confirmed_at: datetime
    entries: list[CheckinEntryOut]
