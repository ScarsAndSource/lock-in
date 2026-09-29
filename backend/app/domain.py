"""
Plain-Python domain entities, deliberately decoupled from SQLAlchemy.

The defaults engine (services/defaults_service.py) is the most important
piece of logic in this slice — it's the core differentiator from every
competitor researched in SPEC.md section 3. It needs to be fully unit
testable without spinning up Postgres, which means it must not import
anything ORM-shaped. Everything in this file exists to make that possible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
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
    Two shapes, matching the check constraint documented in the migration:
      - weekdays:   specific days of the week (0=Monday .. 6=Sunday)
      - n_per_week: a count with no fixed days

    n_per_week habits still get a same-weekday default proposed (see
    defaults_service) — the alternative (no default at all) would defeat
    the point of the opt-out check-in for exactly the habits where "same
    as usual" is hardest to intuit.
    """
    type: Literal["weekdays", "n_per_week"]
    days: tuple[int, ...] = field(default_factory=tuple)  # used when type == "weekdays"
    count: int | None = None  # used when type == "n_per_week"

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
    A *proposed* status for a habit on a date that has no real log yet.
    Never persisted as-is — either confirmed as-is (becomes a HabitLog with
    is_default=True) or overridden by the user (becomes is_default=False).
    """
    habit_id: UUID
    status: HabitStatus
    is_low_confidence: bool
    based_on_count: int
    reason: str


@dataclass(slots=True)
class DailyCheckin:
    user_id: UUID
    checkin_date: date
    journal_encrypted: bytes | None = None
    defaults_applied: dict = field(default_factory=dict)
    confirmed_at: datetime | None = None
