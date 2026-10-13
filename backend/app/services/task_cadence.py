"""
Pure cadence engine (no I/O, no clock): given a task and the user's LOCAL today, is it due?

Design rules, on purpose:
- Only the LATEST occurrence of a weekly/monthly task can be overdue. Missing three Sundays leaves one
  due task, not a pile of three. Nothing accumulates, nothing resets to zero (SPEC section 5).
- An interval task is measured from the last time it was HANDLED (done or skipped), not from a calendar:
  "laundry every 4 days" means 4 days after the last wash. A brand-new interval task is due right away.
- A skip counts as handled for the current occurrence but is not recorded as done.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain_tasks import Cadence, Task

_DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
FULL_DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True, slots=True)
class DueState:
    due: bool
    due_on: date | None        # the occurrence that is currently due (None when not due)
    days_overdue: int          # 0 on the day it falls due
    ratio: float               # how far past due, for ranking: ~1.0 = just due, grows as it drifts
    next_due_on: date | None   # when it next becomes due (None when already due)


_NOT_DUE = DueState(False, None, 0, 0.0, None)


def _month_occurrence(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def latest_occurrence(cadence: Cadence, on_or_before: date) -> date | None:
    """Most recent scheduled date <= on_or_before (weekly / monthly only)."""
    if cadence.kind == "weekly":
        for back in range(7):
            day = on_or_before - timedelta(days=back)
            if day.weekday() in cadence.days:
                return day
        return None
    if cadence.kind == "monthly":
        assert cadence.day_of_month is not None
        this = _month_occurrence(on_or_before.year, on_or_before.month, cadence.day_of_month)
        if this <= on_or_before:
            return this
        y, m = _prev_month(on_or_before.year, on_or_before.month)
        return _month_occurrence(y, m, cadence.day_of_month)
    return None


def next_occurrence_after(cadence: Cadence, after: date) -> date | None:
    """First scheduled date > after (weekly / monthly only)."""
    if cadence.kind == "weekly":
        for ahead in range(1, 8):
            day = after + timedelta(days=ahead)
            if day.weekday() in cadence.days:
                return day
        return None
    if cadence.kind == "monthly":
        assert cadence.day_of_month is not None
        this = _month_occurrence(after.year, after.month, cadence.day_of_month)
        if this > after:
            return this
        y, m = _next_month(after.year, after.month)
        return _month_occurrence(y, m, cadence.day_of_month)
    return None


def evaluate(task: Task, today: date) -> DueState:
    """Is `task` due on the user's local `today`? Snooze is NOT considered here (see is_snoozed)."""
    if task.status != "active":
        return _NOT_DUE
    c = task.cadence
    handled = task.last_handled_on

    if c.kind == "once":
        due_on = c.due_date or task.created_on
        if today < due_on:
            return DueState(False, None, 0, 0.0, due_on)
        overdue = (today - due_on).days
        return DueState(True, due_on, overdue, 1.0 + overdue / 7.0, None)

    if c.kind in ("weekly", "monthly"):
        occ = latest_occurrence(c, today)
        if occ is not None and occ >= task.created_on and (handled is None or handled < occ):
            overdue = (today - occ).days
            return DueState(True, occ, overdue, 1.0 + overdue / 7.0, None)
        return DueState(False, None, 0, 0.0, next_occurrence_after(c, today))

    # interval
    n = c.every_days or 1
    if handled is None:
        due_on = task.created_on
        elapsed = (today - due_on).days
        if elapsed < 0:  # created "in the future" can't happen for real data; stay safe
            return DueState(False, None, 0, 0.0, due_on)
        return DueState(True, due_on, elapsed, 1.0 + elapsed / n, None)
    due_on = handled + timedelta(days=n)
    if today < due_on:
        return DueState(False, None, 0, 0.0, due_on)
    return DueState(True, due_on, (today - due_on).days, (today - handled).days / n, None)


def is_snoozed(task: Task, now: datetime) -> bool:
    return task.snooze_until is not None and task.snooze_until > now


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def describe(c: Cadence) -> str:
    """Short human label, used by the API so every client says the same thing."""
    if c.kind == "once":
        if c.due_date is None:
            return "Whenever"
        return f"Once · {c.due_date.strftime('%b')} {c.due_date.day}"
    if c.kind == "weekly":
        if len(c.days) == 7:
            return "Every day"
        if c.days == (0, 1, 2, 3, 4):
            return "Weekdays"
        if c.days == (5, 6):
            return "Weekends"
        return "Every " + ", ".join(_DAY_NAMES[d] for d in c.days)
    if c.kind == "interval":
        n = c.every_days or 1
        if n == 1:
            return "Every day"
        if n == 7:
            return "Every week"
        if n % 7 == 0:
            return f"Every {n // 7} weeks"
        return f"Every {n} days"
    return f"Monthly on the {_ordinal(c.day_of_month or 1)}"
