"""
"Is this habit supposed to happen today?" -- pure, shared by the defaults
engine, the consistency engine, and the chain.

  - weekdays:   scheduled only on its listed weekdays.
  - n_per_week: scheduled until the week's target (Mon-Sun) is met by logged
                credit (done=1, partial=0.5). After that the rest of the week
                is a free pass -- you hit the number, nothing more is asked.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain import HabitLog, HabitStatus, TargetFrequency

_CREDIT = {HabitStatus.DONE: 1.0, HabitStatus.PARTIAL: 0.5, HabitStatus.SKIPPED: 0.0}


def credit(status: HabitStatus) -> float:
    return _CREDIT[status]


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


@dataclass(frozen=True, slots=True)
class ScheduleVerdict:
    scheduled: bool
    reason: str = ""


def check_scheduled(freq: TargetFrequency, target_date: date, history: Iterable[HabitLog]) -> ScheduleVerdict:
    if freq.type == "weekdays":
        if target_date.weekday() in freq.days:
            return ScheduleVerdict(True)
        return ScheduleVerdict(False, "Not a scheduled day for this habit.")

    ws = week_start(target_date)
    earned = sum(credit(log.status) for log in history if ws <= log.log_date < target_date)
    if earned >= freq.count:
        return ScheduleVerdict(False, f"Weekly target ({freq.count}) already met.")
    return ScheduleVerdict(True)
