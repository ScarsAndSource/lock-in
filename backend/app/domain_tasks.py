"""
Plain-Python domain entities for the life-admin lane: tasks, their cadence, nudge preferences,
push subscriptions and the nudge log. No SQLAlchemy here, so the cadence and nudge engines stay pure.

Nothing in this module knows what a task IS ("call nani", "laundry"): titles are user data, and the
schedule is a small structured Cadence the user (or the parser) fills in. No built-in task list exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from uuid import UUID

IMPORTANCES = ("low", "normal", "high")
TASK_STATUSES = ("active", "done", "archived")
CADENCE_KINDS = ("once", "weekly", "interval", "monthly")
EVENT_KINDS = ("done", "skip")
NUDGE_KINDS = ("task", "digest", "ask")


@dataclass(frozen=True, slots=True)
class Cadence:
    """
    once      one-off, optional due_date (None = "whenever", it just sits on the list)
    weekly    fixed weekdays (0=Monday .. 6=Sunday)
    interval  every N days counted from the last time it was handled ("laundry ~every 4 days")
    monthly   day of month (1..31, clamped to the month's last day)
    """
    kind: str
    days: tuple[int, ...] = ()
    every_days: int | None = None
    day_of_month: int | None = None
    due_date: date | None = None

    def __post_init__(self) -> None:
        if self.kind not in CADENCE_KINDS:
            raise ValueError(f"unknown cadence kind: {self.kind!r}")
        if self.kind == "weekly":
            if not self.days or any((not isinstance(d, int)) or isinstance(d, bool) or d < 0 or d > 6 for d in self.days):
                raise ValueError("weekly cadence needs at least one weekday between 0 (Mon) and 6 (Sun)")
        elif self.kind == "interval":
            e = self.every_days
            if not isinstance(e, int) or isinstance(e, bool) or e < 1 or e > 365:
                raise ValueError("interval cadence needs every_days between 1 and 365")
        elif self.kind == "monthly":
            m = self.day_of_month
            if not isinstance(m, int) or isinstance(m, bool) or m < 1 or m > 31:
                raise ValueError("monthly cadence needs a day between 1 and 31")

    @classmethod
    def from_dict(cls, data: Any) -> "Cadence":
        if not isinstance(data, dict):
            raise ValueError("cadence must be an object")
        kind = data.get("kind")
        if kind == "once":
            raw = data.get("due_date")
            due: date | None = None
            if raw not in (None, ""):
                if isinstance(raw, date) and not isinstance(raw, datetime):
                    due = raw
                elif isinstance(raw, str):
                    try:
                        due = date.fromisoformat(raw[:10])
                    except ValueError as exc:
                        raise ValueError("due_date must be YYYY-MM-DD") from exc
                else:
                    raise ValueError("due_date must be YYYY-MM-DD")
            return cls("once", due_date=due)
        if kind == "weekly":
            days = data.get("days")
            if not isinstance(days, (list, tuple)):
                raise ValueError("weekly cadence needs a days list")
            try:
                clean = tuple(sorted(set(days)))
            except TypeError as exc:
                raise ValueError("weekly days must be whole numbers 0-6") from exc
            return cls("weekly", days=clean)
        if kind == "interval":
            return cls("interval", every_days=data.get("every_days"))
        if kind == "monthly":
            return cls("monthly", day_of_month=data.get("day"))
        raise ValueError(f"unknown cadence kind: {kind!r}")

    def to_dict(self) -> dict[str, Any]:
        if self.kind == "once":
            return {"kind": "once", "due_date": self.due_date.isoformat() if self.due_date else None}
        if self.kind == "weekly":
            return {"kind": "weekly", "days": list(self.days)}
        if self.kind == "interval":
            return {"kind": "interval", "every_days": self.every_days}
        return {"kind": "monthly", "day": self.day_of_month}


@dataclass(slots=True)
class Task:
    id: UUID
    user_id: UUID
    title_encrypted: bytes
    cadence: Cadence
    created_on: date          # the user's LOCAL date at creation; anchors the cadence
    created_at: datetime
    importance: str = "normal"
    status: str = "active"
    preferred_time: time | None = None   # local; no nudge before this time of day
    nudge_enabled: bool = True
    snooze_until: datetime | None = None
    last_done_on: date | None = None
    last_handled_on: date | None = None   # done OR skipped
    unanswered_nudges: int = 0
    last_nudged_at: datetime | None = None


@dataclass(slots=True)
class TaskEvent:
    id: UUID
    user_id: UUID
    task_id: UUID
    event_date: date          # the user's LOCAL date
    kind: str                 # done | skip
    created_at: datetime


@dataclass(slots=True)
class NudgePrefs:
    user_id: UUID
    enabled: bool = True
    quiet_start: time = time(22, 0)
    quiet_end: time = time(8, 0)
    max_per_day: int = 3
    digest_time: time = time(18, 30)


@dataclass(slots=True)
class PushSubscription:
    id: UUID
    user_id: UUID
    endpoint: str
    p256dh: str
    auth: str
    created_at: datetime
    user_agent: str | None = None
    failure_count: int = 0
    last_success_at: datetime | None = None


@dataclass(slots=True)
class NudgeLog:
    id: UUID
    user_id: UUID
    local_date: date
    sent_at: datetime
    kind: str                 # task | digest | ask
    task_ids: tuple[UUID, ...] = ()
    delivered: int = 0
