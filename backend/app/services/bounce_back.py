"""
Bounce-back protocol -- "never miss twice".

The costly moment in habit tracking is not the miss, it's the story after it
("already blew it, so whatever"). After a slip the next check-in shrinks to a
minimum viable day: unlogged habits are proposed at their FLOOR instead of
their usual status, and the app says so plainly.

All functions are pure (no DB, no clock, no network).

  day states (computed per calendar day from the user's own logs)
    rest   nothing was scheduled (or everything was paused)
    held   logged credit / scheduled habits >= 0.5   (a floor day counts as held)
    slip   below that, INCLUDING scheduled habits nobody logged (an absent day)

  scheduled-ness follows chain_service.habit_day: weekday habits are scheduled
  on their weekdays; an n_per_week habit only counts on days it was logged.
  Habits created after a day never count against that day; paused habit-days
  are skipped unless the user logged them anyway.

  BounceState  looks back from the target date over NON-rest days: if the most
               recent one slipped, today is a bounce day. slip_streak counts
               consecutive slipped non-rest days (capped), so a three-day
               absence is handled the same way as a single miss, just gentler.
               A user with no logs at all (brand new) is never in bounce.

  bounce_rate  the north-star metric: of the slip days that have had a full
               48h to resolve, the share followed by a held day within 2 days.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from app.domain import HabitDefinition, HabitLog
from app.services.schedule import check_scheduled, credit

SLIP, HELD, REST = "slip", "held", "rest"

LOOKBACK_DAYS = 14        # how far back a bounce check will look for the last scheduled day
MAX_STREAK = 7
HELD_RATIO = 0.5          # same threshold chain_service uses for "OK" vs "BAD"
RETURN_WINDOW_DAYS = 2    # "within 48 hours"


@dataclass(frozen=True, slots=True)
class BounceState:
    active: bool
    slip_streak: int = 0
    last_slip_date: date | None = None


INACTIVE = BounceState(active=False)


@dataclass(frozen=True, slots=True)
class BounceRate:
    slip_days: int           # slip days old enough to judge
    returned: int            # of those, how many saw a held day within 48h
    rate_pct: float | None   # None when there is nothing to judge yet


def _index(logs: Iterable[HabitLog]) -> dict[UUID, dict[date, HabitLog]]:
    out: dict[UUID, dict[date, HabitLog]] = {}
    for log in logs:
        out.setdefault(log.habit_id, {})[log.log_date] = log
    return out


def classify_day(
    habits: list[HabitDefinition],
    by_habit: Mapping[UUID, Mapping[date, HabitLog]],
    day: date,
    paused_global: frozenset[date] = frozenset(),
    paused_by_habit: Mapping[UUID, frozenset[date]] | None = None,
) -> str:
    paused_by_habit = paused_by_habit or {}
    scheduled, earned = 0, 0.0
    for habit in habits:
        if habit.created_at.date() > day:
            continue
        log = by_habit.get(habit.id, {}).get(day)
        if log is None:
            if day in paused_global or day in paused_by_habit.get(habit.id, frozenset()):
                continue
            if habit.target_frequency.type == "n_per_week":
                continue  # a flexible habit is only "owed" on days the user logged it
            if not check_scheduled(habit.target_frequency, day, ()).scheduled:
                continue
        scheduled += 1
        if log is not None:
            earned += credit(log.status)
    if scheduled == 0:
        return REST
    return HELD if earned / scheduled >= HELD_RATIO else SLIP


def classify_range(
    habits: list[HabitDefinition],
    logs: Iterable[HabitLog],
    start: date,
    end: date,
    paused_global: frozenset[date] = frozenset(),
    paused_by_habit: Mapping[UUID, frozenset[date]] | None = None,
) -> dict[date, str]:
    by_habit = _index(logs)
    states: dict[date, str] = {}
    day = start
    while day <= end:
        states[day] = classify_day(habits, by_habit, day, paused_global, paused_by_habit)
        day += timedelta(days=1)
    return states


def compute_bounce_state(
    habits: list[HabitDefinition],
    logs: Iterable[HabitLog],
    target_date: date,
    paused_global: frozenset[date] = frozenset(),
    paused_by_habit: Mapping[UUID, frozenset[date]] | None = None,
) -> BounceState:
    logs = [l for l in logs if l.log_date < target_date]
    if not habits or not logs:
        return INACTIVE  # nothing to bounce back FROM yet
    first = target_date - timedelta(days=LOOKBACK_DAYS)
    states = classify_range(habits, logs, first, target_date - timedelta(days=1), paused_global, paused_by_habit)
    streak, last_slip = 0, None
    day = target_date - timedelta(days=1)
    while day >= first and streak < MAX_STREAK:
        state = states[day]
        if state == SLIP:
            streak += 1
            last_slip = last_slip or day
        elif state == HELD:
            break
        day -= timedelta(days=1)  # rest days are skipped, not counted
    if streak == 0:
        return INACTIVE
    return BounceState(active=True, slip_streak=streak, last_slip_date=last_slip)


def compute_bounce_rate(states: Mapping[date, str], end: date) -> BounceRate:
    judged = returned = 0
    for day, state in states.items():
        if state != SLIP or day + timedelta(days=RETURN_WINDOW_DAYS) > end:
            continue
        judged += 1
        if any(states.get(day + timedelta(days=k)) == HELD for k in range(1, RETURN_WINDOW_DAYS + 1)):
            returned += 1
    return BounceRate(judged, returned, round(100.0 * returned / judged, 1) if judged else None)


# ---------------------------------------------------------------- copy
BOUNCE_REASON = "Bounce-back day: the floor counts. Just don't miss twice."

_COPY = {
    ("direct", False): (
        "Floor day",
        "Yesterday slipped. Today the floor counts: the smallest version of each habit keeps the chain going. "
        "Don't miss twice.",
    ),
    ("direct", True): (
        "Floor day, again",
        "More than one scheduled day slipped. Today is floor only. One small win breaks the run.",
    ),
    ("coach", False): (
        "Easy day today",
        "Yesterday didn't land, and that's just data about the day. Today the floor counts: "
        "the smallest version of each habit keeps you in it.",
    ),
    ("coach", True): (
        "Start small",
        "A few days slipped and nothing is lost. Today is floor only. One small win is enough to turn it around.",
    ),
}


def bounce_copy(state: BounceState, tone: str) -> tuple[str, str] | None:
    """(title, message) for the check-in card, or None when there is no bounce."""
    if not state.active:
        return None
    return _COPY[("coach" if tone == "coach" else "direct", state.slip_streak >= 2)]
