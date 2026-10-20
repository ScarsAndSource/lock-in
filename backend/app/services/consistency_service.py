"""
Rolling consistency -- the "never resets to zero" model. A miss dents a
percentage; it never wipes a counter.

  consistency_pct  earned credit / expected credit in the window
                   (done=1, partial=0.5, skipped/unlogged=0; capped at 100)
  coverage_pct     how much of the window you actually logged (honesty check)
  longest/current  weekday habits: runs over SCHEDULED days, unit "days".
                   n_per_week habits: runs of consecutive weeks meeting the
                   target, unit "weeks".
  comeback_rate    after a missed scheduled day, how often the NEXT scheduled
                   day was not a miss. Weekday habits only. The metric that
                   rewards bouncing back instead of punishing the dip.

If end_date is itself a scheduled day not yet logged, it's PENDING, not a miss.

A habit is only judged from the day it started existing: the window is clamped to `habit_start`
(the habit's creation day in the user's timezone), or to the earliest real log if the user backfilled
before that. Days before the habit existed are neither misses nor expected credit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from app.domain import HabitDefinition, HabitLog, HabitStatus
from app.services.schedule import credit, week_start


@dataclass(slots=True)
class HabitConsistency:
    habit_id: UUID
    habit_name: str
    window_days: int
    consistency_pct: float | None
    expected: float
    earned: float
    logged_days: int
    coverage_pct: float | None
    longest_run: int
    current_run: int
    run_unit: str
    comeback_rate: float | None


def _is_miss(log: HabitLog | None) -> bool:
    return log is None or log.status == HabitStatus.SKIPPED


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(min(100.0, 100.0 * numerator / denominator), 1)


def compute_habit_consistency(
    habit: HabitDefinition,
    logs: list[HabitLog],
    end_date: date,
    window_days: int,
    paused_days: frozenset[date] = frozenset(),
    habit_start: date | None = None,
) -> HabitConsistency:
    if window_days < 1:
        raise ValueError("window_days must be >= 1")
    start = end_date - timedelta(days=window_days - 1)
    by_date = {
        l.log_date: l
        for l in logs
        if l.habit_id == habit.id and not l.is_default and start <= l.log_date <= end_date
    }
    if habit_start is not None:
        # Judge the habit only from the day it began (or its earliest real log, if backfilled earlier).
        began = min([habit_start, *by_date]) if by_date else habit_start
        start = max(start, min(began, end_date))
    if habit.target_frequency.type == "weekdays":
        return _weekdays(habit, by_date, start, end_date, window_days, paused_days)
    return _n_per_week(habit, by_date, start, end_date, window_days, paused_days)


def _weekdays(
    habit, by_date, start, end_date, window_days, paused_days: frozenset[date] = frozenset()
) -> HabitConsistency:
    days = [start + timedelta(days=i) for i in range((end_date - start).days + 1)]
    scheduled = [d for d in days if d.weekday() in habit.target_frequency.days]
    evaluated = [
        d for d in scheduled
        if (d not in paused_days or d in by_date) and not (d == end_date and d not in by_date)
    ]

    expected = float(len(evaluated))
    earned = sum(credit(by_date[d].status) for d in evaluated if d in by_date)
    logged = sum(1 for d in evaluated if d in by_date)

    longest = current = 0
    for d in evaluated:
        log = by_date.get(d)
        if log is not None and log.status != HabitStatus.SKIPPED:
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    chances = [i for i, d in enumerate(evaluated[:-1]) if _is_miss(by_date.get(d))]
    recovered = sum(1 for i in chances if not _is_miss(by_date.get(evaluated[i + 1])))
    comeback = round(100.0 * recovered / len(chances), 1) if chances else None

    return HabitConsistency(
        habit_id=habit.id, habit_name=habit.name, window_days=window_days,
        consistency_pct=_pct(earned, expected), expected=expected, earned=earned,
        logged_days=logged, coverage_pct=_pct(logged, expected),
        longest_run=longest, current_run=current, run_unit="days", comeback_rate=comeback,
    )


def _n_per_week(
    habit, by_date, start, end_date, window_days, paused_days: frozenset[date] = frozenset()
) -> HabitConsistency:
    target = habit.target_frequency.count
    span = (end_date - start).days + 1
    days = [start + timedelta(days=i) for i in range(span)]
    active_days = sum(1 for d in days if d not in paused_days or d in by_date)
    expected = target * active_days / 7
    total_credit = sum(credit(l.status) for l in by_date.values())
    earned = min(total_credit, expected)

    # Weeks fully inside the window, plus the in-progress current week.
    weeks: list[tuple[date, bool]] = []
    w = week_start(start)
    if w < start:
        w += timedelta(days=7)
    while w + timedelta(days=6) <= end_date:
        weeks.append((w, False))
        w += timedelta(days=7)
    if w <= end_date:
        weeks.append((w, True))

    longest = current = 0
    for ws, in_progress in weeks:
        week_credit = sum(
            credit(by_date[ws + timedelta(days=i)].status)
            for i in range(7) if (ws + timedelta(days=i)) in by_date
        )
        if week_credit >= target:
            current += 1
            longest = max(longest, current)
        elif in_progress:
            continue  # not over yet -- not a miss
        else:
            current = 0

    return HabitConsistency(
        habit_id=habit.id, habit_name=habit.name, window_days=window_days,
        consistency_pct=_pct(earned, expected), expected=expected, earned=earned,
        logged_days=len(by_date), coverage_pct=_pct(len(by_date), span),
        longest_run=longest, current_run=current, run_unit="weeks", comeback_rate=None,
    )


def overall_consistency(items: list[HabitConsistency]) -> float | None:
    values = [i.consistency_pct for i in items if i.consistency_pct is not None]
    return round(sum(values) / len(values), 1) if values else None
