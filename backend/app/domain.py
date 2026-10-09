"""
Plain-Python domain entities, decoupled from SQLAlchemy so the engines
(defaults, consistency, chain, patterns, missions) are pure and unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Literal
from uuid import UUID


class HabitStatus(str, Enum):
    DONE = "done"
    SKIPPED = "skipped"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class TargetFrequency:
    """
      - weekdays:   specific days (0=Monday .. 6=Sunday)
      - n_per_week: a count with no fixed days (resets every Monday)
    """
    type: Literal["weekdays", "n_per_week"]
    days: tuple[int, ...] = field(default_factory=tuple)
    count: int | None = None

    def __post_init__(self):
        if self.type == "weekdays":
            if not self.days:
                raise ValueError("weekdays frequency requires at least one day")
            if any(d < 0 or d > 6 for d in self.days):
                raise ValueError("weekday values must be 0 (Mon) through 6 (Sun)")
        elif self.type == "n_per_week":
            if not self.count or self.count < 1 or self.count > 7:
                raise ValueError("n_per_week count must be between 1 and 7")
        else:
            raise ValueError(f"unknown target_frequency type: {self.type!r}")

    def to_dict(self) -> dict:
        if self.type == "weekdays":
            return {"type": "weekdays", "days": list(self.days)}
        return {"type": "n_per_week", "count": self.count}

    @classmethod
    def from_dict(cls, data: dict) -> "TargetFrequency":
        if data["type"] == "weekdays":
            return cls(type="weekdays", days=tuple(data["days"]))
        return cls(type="n_per_week", count=data["count"])


@dataclass(slots=True)
class HabitDefinition:
    id: UUID
    user_id: UUID
    name: str
    target_frequency: TargetFrequency
    created_at: datetime
    archived_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.archived_at is None


@dataclass(slots=True)
class HabitLog:
    habit_id: UUID
    user_id: UUID
    log_date: date
    status: HabitStatus
    note: str | None = None
    is_default: bool = False


@dataclass(slots=True)
class HabitDefault:
    """
    A PROPOSED status for a habit on a date with no real log. status is None and
    is_scheduled False on rest days (weekday habit on an off-day, or an
    n_per_week habit whose weekly target is already met): nothing is proposed
    and nothing is written unless the user overrides.
    """
    habit_id: UUID
    status: HabitStatus | None
    is_low_confidence: bool
    based_on_count: int
    reason: str
    is_scheduled: bool = True


@dataclass(slots=True)
class DailyCheckin:
    user_id: UUID
    checkin_date: date
    journal_encrypted: bytes | None = None
    defaults_applied: dict = field(default_factory=dict)
    confirmed_at: datetime | None = None


class ScreenTimeSource(str, Enum):
    MANUAL = "manual"
    EXTENSION = "extension"


@dataclass(slots=True)
class SleepLog:
    """
    log_date = the date the user WOKE UP. All fields optional; a partial log is
    valid. is_default=True marks a log auto-filled from "same as usual" -- the
    insight/pattern engines ignore those so guesses never become "evidence".
    """
    user_id: UUID
    log_date: date
    time_to_bed: time | None = None
    time_woke: time | None = None
    self_rated_quality: int | None = None  # 1-5
    is_default: bool = False

    def __post_init__(self):
        if self.self_rated_quality is not None and not (1 <= self.self_rated_quality <= 5):
            raise ValueError("self_rated_quality must be between 1 and 5")

    @property
    def duration_minutes(self) -> int | None:
        if self.time_to_bed is None or self.time_woke is None:
            return None
        bed = self.time_to_bed.hour * 60 + self.time_to_bed.minute
        wake = self.time_woke.hour * 60 + self.time_woke.minute
        if wake <= bed:
            wake += 24 * 60
        return wake - bed


@dataclass(slots=True)
class ScreenTimeLog:
    user_id: UUID
    log_date: date
    total_minutes: int
    source: ScreenTimeSource
    category_breakdown: dict | None = None
    is_default: bool = False

    def __post_init__(self):
        if self.total_minutes < 0:
            raise ValueError("total_minutes must be >= 0")


@dataclass(slots=True)
class SleepProposal:
    time_to_bed: time | None
    time_woke: time | None
    self_rated_quality: int | None
    based_on_count: int
    is_low_confidence: bool
    reason: str


@dataclass(slots=True)
class ScreenTimeProposal:
    total_minutes: int
    based_on_count: int
    is_low_confidence: bool
    reason: str


@dataclass(slots=True)
class Profile:
    user_id: UUID
    timezone: str
    tone_preference: str


class MissionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ENDED_EARLY = "ended_early"


@dataclass(slots=True)
class Mission:
    id: UUID
    user_id: UUID
    title: str
    start_date: date
    end_date: date
    status: MissionStatus
    created_at: datetime
    ended_at: datetime | None = None


@dataclass(slots=True)
class WeeklyRetro:
    """summary = exactly the facts the narration was built from (deterministic, JSON-safe)."""
    id: UUID
    user_id: UUID
    week_start: date
    week_end: date
    generated_at: datetime
    narrative: str
    next_step: str
    summary: dict
    evidence_refs: dict
    narrated: bool
    voice_version: str
    model: str | None
    completed_at: datetime | None = None


@dataclass(slots=True)
class PatternInsight:
    """Stub for slice 8: full insights slice is later."""
    id: UUID
    user_id: UUID
    generated_at: datetime
    generated_on: date
    pattern_key: str
    insight_text: str
    next_step: str
    source_domains: list[str]
    evidence_refs: dict
    narrated: bool
    voice_version: str
    model: str | None
    user_feedback: str | None = None


@dataclass(slots=True)
class Subject:
    id: UUID
    user_id: UUID
    name: str
    created_at: datetime
    archived_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.archived_at is None


@dataclass(slots=True)
class StudySession:
    id: UUID
    user_id: UUID
    subject_id: UUID
    log_date: date
    actual_minutes: int
    planned_minutes: int | None = None


class UrgeOutcome(str, Enum):
    RESISTED = "resisted"
    RELAPSED = "relapsed"


@dataclass(slots=True)
class UrgeLog:
    """Free-text fields are held ENCRYPTED here; the service encrypts/decrypts."""
    id: UUID
    user_id: UUID
    occurred_at: datetime
    log_date: date
    outcome: UrgeOutcome
    intensity: int | None = None
    trigger_context_encrypted: bytes | None = None
    coping_strategy_encrypted: bytes | None = None
    note_encrypted: bytes | None = None

    @property
    def has_detail(self) -> bool:
        return any((
            self.intensity, self.trigger_context_encrypted,
            self.coping_strategy_encrypted, self.note_encrypted,
        ))


GOAL_DOMAINS = ("habit", "screen_time", "urge", "study", "sleep")


class GoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ACHIEVED = "achieved"
    ARCHIVED = "archived"


@dataclass(slots=True)
class Goal:
    id: UUID
    user_id: UUID
    domain: str
    definition: str
    target: dict
    status: GoalStatus
    created_at: datetime


@dataclass(slots=True)
class Intention:
    id: UUID
    user_id: UUID
    linked_domain: str
    cue: str
    action: str
    created_at: datetime
    linked_entity_id: UUID | None = None
    active: bool = True


