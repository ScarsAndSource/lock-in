from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain import HabitStatus, MissionStatus, ScreenTimeSource


# ---------------------------------------------------------------- habits
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


TargetFrequencyIn = Annotated[WeekdaysFrequency | NPerWeekFrequency, Field(discriminator="type")]


class HabitCreateRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    target_frequency: TargetFrequencyIn


class HabitPatchRequest(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    archived: bool | None = None
    target_frequency: TargetFrequencyIn | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "HabitPatchRequest":
        if self.name is None and self.archived is None and self.target_frequency is None:
            raise ValueError("Provide at least one of: name, archived, target_frequency")
        return self


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


# ---------------------------------------------------------------- sleep
class SleepLogRequest(BaseModel):
    log_date: date
    time_to_bed: time | None = None
    time_woke: time | None = None
    self_rated_quality: Annotated[int | None, Field(ge=1, le=5)] = None


class SleepLogOut(BaseModel):
    log_date: date
    time_to_bed: time | None
    time_woke: time | None
    self_rated_quality: int | None
    duration_minutes: int | None
    is_default: bool = False


# ---------------------------------------------------------------- screen time
_MAX_BREAKDOWN_KEYS = 30


def _validate_breakdown(v: dict | None) -> dict | None:
    """{category: minutes}: <=30 keys, names 1-40 chars, whole minutes 0-1440. No free-form blobs."""
    if v is None:
        return v
    if len(v) > _MAX_BREAKDOWN_KEYS:
        raise ValueError(f"category_breakdown can have at most {_MAX_BREAKDOWN_KEYS} categories")
    for key, minutes in v.items():
        if not isinstance(key, str) or not 1 <= len(key) <= 40:
            raise ValueError("category names must be 1-40 characters")
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 <= minutes <= 1440:
            raise ValueError("category minutes must be whole numbers between 0 and 1440")
    return v


class ScreenTimeLogRequest(BaseModel):
    log_date: date
    total_minutes: Annotated[int, Field(ge=0, le=1440)]
    source: ScreenTimeSource
    category_breakdown: dict | None = None

    _check_breakdown = field_validator("category_breakdown")(_validate_breakdown)


class ScreenTimeLogOut(BaseModel):
    log_date: date
    total_minutes: int
    source: ScreenTimeSource
    category_breakdown: dict | None
    is_default: bool = False


# ---------------------------------------------------------------- check-in
class CheckinEntryOut(BaseModel):
    habit_id: UUID
    habit_name: str
    status: HabitStatus | None  # None on rest days
    is_default: bool
    is_low_confidence: bool
    reason: str
    is_scheduled: bool = True


class SleepProposalOut(BaseModel):
    time_to_bed: time | None
    time_woke: time | None
    self_rated_quality: int | None
    based_on_count: int
    is_low_confidence: bool
    reason: str


class ScreenTimeProposalOut(BaseModel):
    total_minutes: int
    based_on_count: int
    is_low_confidence: bool
    reason: str


class SleepSectionOut(BaseModel):
    logged: SleepLogOut | None
    proposal: SleepProposalOut | None


class ScreenTimeSectionOut(BaseModel):
    logged: ScreenTimeLogOut | None
    proposal: ScreenTimeProposalOut | None


class CheckinViewOut(BaseModel):
    checkin_date: date
    already_confirmed: bool
    entries: list[CheckinEntryOut]
    sleep: SleepSectionOut
    screen_time: ScreenTimeSectionOut


class CheckinOverrideIn(BaseModel):
    habit_id: UUID
    status: HabitStatus
    note: Annotated[str | None, Field(max_length=2000)] = None


class SleepEntryIn(BaseModel):
    time_to_bed: time | None = None
    time_woke: time | None = None
    self_rated_quality: Annotated[int | None, Field(ge=1, le=5)] = None

    @model_validator(mode="after")
    def _not_empty(self) -> "SleepEntryIn":
        if self.time_to_bed is None and self.time_woke is None and self.self_rated_quality is None:
            raise ValueError("A sleep entry needs at least one field")
        return self


class ScreenTimeEntryIn(BaseModel):
    total_minutes: Annotated[int, Field(ge=0, le=1440)]
    source: ScreenTimeSource = ScreenTimeSource.MANUAL
    category_breakdown: dict | None = None

    _check_breakdown = field_validator("category_breakdown")(_validate_breakdown)


class CheckinConfirmRequest(BaseModel):
    overrides: list[CheckinOverrideIn] = Field(default_factory=list)
    # None = leave the existing journal untouched. "" = clear it.
    journal_text: Annotated[str | None, Field(max_length=10_000)] = None
    sleep: SleepEntryIn | None = None
    screen_time: ScreenTimeEntryIn | None = None
    accept_sleep_default: bool = True
    accept_screen_time_default: bool = True

    @field_validator("overrides")
    @classmethod
    def _no_duplicate_habit_overrides(cls, v: list[CheckinOverrideIn]) -> list[CheckinOverrideIn]:
        ids = [o.habit_id for o in v]
        if len(ids) != len(set(ids)):
            raise ValueError("overrides must not reference the same habit_id more than once")
        return v


class CheckinConfirmOut(BaseModel):
    checkin_date: date
    confirmed_at: datetime
    entries: list[CheckinEntryOut]
    sleep: SleepLogOut | None
    screen_time: ScreenTimeLogOut | None


class JournalOut(BaseModel):
    checkin_date: date
    journal_text: str | None


# ---------------------------------------------------------------- stats
class HabitConsistencyOut(BaseModel):
    habit_id: UUID
    habit_name: str
    consistency_pct: float | None
    coverage_pct: float | None
    longest_run: int
    current_run: int
    run_unit: Literal["days", "weeks"]
    comeback_rate: float | None


class ConsistencyOut(BaseModel):
    end_date: date
    window_days: int
    overall_pct: float | None
    habits: list[HabitConsistencyOut]


class ChainDayOut(BaseModel):
    day: date
    habits: str
    sleep: str
    screen_time: str
    habit_ratio: float | None
    sleep_minutes: int | None
    screen_minutes: int | None
    sleep_defaulted: bool
    screen_time_defaulted: bool
    habits_defaulted: bool = False


class ChainOut(BaseModel):
    end_date: date
    days: list[ChainDayOut]


class PatternOut(BaseModel):
    key: str
    trigger: str
    outcome: str
    lag_days: int
    trigger_days: int
    hits: int
    rate_after_trigger: float
    baseline_days: int
    baseline_rate: float
    evidence_dates: list[date]
    statement: str


class PatternsOut(BaseModel):
    end_date: date
    days: int
    patterns: list[PatternOut]


# ---------------------------------------------------------------- missions
class MissionCreateRequest(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    duration_days: Annotated[int, Field(ge=7, le=365)]
    start_date: date | None = None


class MissionOut(BaseModel):
    id: UUID
    title: str
    start_date: date
    end_date: date
    status: MissionStatus
    ended_at: datetime | None


class CheckpointOut(BaseModel):
    label: str
    day: int
    checkpoint_date: date


class MissionProgressOut(BaseModel):
    state: Literal["upcoming", "running", "finished"]
    day_number: int
    days_total: int
    days_left: int
    elapsed_pct: float
    phase: str | None
    next_checkpoint: CheckpointOut | None


class MissionDetailOut(BaseModel):
    mission: MissionOut
    progress: MissionProgressOut
    consistency_pct: float | None
    habits: list[HabitConsistencyOut]


class MissionEndRequest(BaseModel):
    completed: bool


# ---------------------------------------------------------------- profile / account
class ProfileOut(BaseModel):
    timezone: str
    tone_preference: str
    today: date


class ProfilePatchRequest(BaseModel):
    timezone: Annotated[str, Field(min_length=1, max_length=64)]


class DeleteAccountRequest(BaseModel):
    confirm: Literal["DELETE MY DATA"]
