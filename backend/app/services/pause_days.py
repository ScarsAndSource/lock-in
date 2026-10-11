from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID


def expand_pause_days(pauses, start: date, end: date) -> frozenset[date]:
    """Every calendar day in [start, end] covered by any of `pauses` (they may overlap)."""
    days: set[date] = set()
    for p in pauses:
        day, last = max(p.start_date, start), min(p.end_date, end)
        while day <= last:
            days.add(day)
            day += timedelta(days=1)
    return frozenset(days)


def split_pause_days(pauses, start: date, end: date) -> tuple[frozenset[date], dict[UUID, frozenset[date]]]:
    """(days where EVERYTHING is paused, {habit_id: days where just that habit is paused})."""
    global_days = expand_pause_days([p for p in pauses if p.habit_id is None], start, end)
    by_habit: dict[UUID, set[date]] = {}
    for p in pauses:
        if p.habit_id is not None:
            by_habit.setdefault(p.habit_id, set()).update(expand_pause_days([p], start, end))
    return global_days, {h: frozenset(days) for h, days in by_habit.items()}
