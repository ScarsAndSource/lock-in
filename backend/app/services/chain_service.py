"""
The chain strip: one row per day, one state per domain
(good / ok / bad / none). Pure -- feeds the UI strip and the pattern finder.

Habit day: weekday-type habits scheduled that day always count (unlogged = 0);
n_per_week habits only count on days they were logged (an unlogged day is a
rest day, not a miss). A day with no habit logs at all is "none".
Sleep: worst of duration (>=7h good, >=6h ok) and quality (>=4 good, 3 ok).
Screen: vs YOUR median once you have 5+ real logs (<=median good, <=1.25x ok);
before that, absolute fallback (<=2h good, <=4h ok).
Auto-filled sleep/screen rows are flagged so patterns can ignore them.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from app.domain import HabitDefinition, HabitLog, ScreenTimeLog, SleepLog
from app.services.schedule import check_scheduled, credit

GOOD, OK, BAD, NONE = "good", "ok", "bad", "none"
_SEVERITY = [GOOD, OK, BAD]
_SCREEN_FALLBACK_MINUTES = (120, 240)
_SCREEN_BASELINE_MIN_LOGS = 5


@dataclass(slots=True)
class ChainDay:
    day: date
    habits: str
    sleep: str
    screen_time: str
    habit_ratio: float | None
    sleep_minutes: int | None
    screen_minutes: int | None
    sleep_defaulted: bool
    screen_time_defaulted: bool
    study: str = NONE
    urges: str = NONE
    habits_defaulted: bool = False


def sleep_state(log: SleepLog | None) -> str:
    if log is None:
        return NONE
    signals = []
    duration = log.duration_minutes
    if duration is not None:
        signals.append(GOOD if duration >= 420 else OK if duration >= 360 else BAD)
    quality = log.self_rated_quality
    if quality is not None:
        signals.append(GOOD if quality >= 4 else OK if quality == 3 else BAD)
    return max(signals, key=_SEVERITY.index) if signals else NONE


def screen_baseline(logs: list[ScreenTimeLog]) -> float | None:
    real = [l.total_minutes for l in logs if not l.is_default]
    return float(statistics.median(real)) if len(real) >= _SCREEN_BASELINE_MIN_LOGS else None


def screen_state(minutes: int | None, baseline: float | None) -> str:
    if minutes is None:
        return NONE
    good_limit, ok_limit = (baseline, baseline * 1.25) if baseline is not None else _SCREEN_FALLBACK_MINUTES
    return GOOD if minutes <= good_limit else OK if minutes <= ok_limit else BAD


def study_state(minutes: int) -> str:
    return GOOD if minutes >= 120 else OK if minutes >= 45 else BAD if minutes > 0 else NONE


def urge_state(outcomes: list[str]) -> str:
    if not outcomes:
        return NONE
    return BAD if "relapsed" in outcomes else GOOD


def study_states_by_day(sessions: list) -> dict[date, int]:
    totals: dict[date, int] = {}
    for s in sessions:
        totals[s.log_date] = totals.get(s.log_date, 0) + s.actual_minutes
    return totals


def urge_states_by_day(logs: list) -> dict[date, list[str]]:
    by_day: dict[date, list[str]] = {}
    for l in logs:
        by_day.setdefault(l.log_date, []).append(l.outcome)
    return by_day


def habit_day(habits: list[HabitDefinition], by_habit: dict[UUID, dict[date, HabitLog]], day: date):
    total, earned, logged = 0, 0.0, 0
    all_defaulted = True
    for habit in habits:
        logs = by_habit.get(habit.id, {})
        log = logs.get(day)
        if log is not None:
            logged += 1
            if not log.is_default:
                all_defaulted = False
        else:
            if habit.target_frequency.type == "n_per_week":
                continue
            history = [l for d, l in logs.items() if d < day]
            if not check_scheduled(habit.target_frequency, day, history).scheduled:
                continue
        total += 1
        earned += credit(log.status) if log is not None else 0.0
    if logged == 0 or total == 0:
        return NONE, None, False
    ratio = earned / total
    is_defaulted = (logged > 0 and all_defaulted)
    return (GOOD if ratio >= 1 else OK if ratio >= 0.5 else BAD), round(ratio, 2), is_defaulted


def build_chain(
    habits: list[HabitDefinition],
    habit_logs: list[HabitLog],
    sleep_logs: list[SleepLog],
    screen_logs: list[ScreenTimeLog],
    start: date,
    end: date,
    study_by_day: dict[date, int] | None = None,
    urge_by_day: dict[date, list[str]] | None = None,
) -> list[ChainDay]:
    by_habit: dict[UUID, dict[date, HabitLog]] = {}
    for log in habit_logs:
        by_habit.setdefault(log.habit_id, {})[log.log_date] = log
    sleep_by = {l.log_date: l for l in sleep_logs}
    screen_by = {l.log_date: l for l in screen_logs}
    baseline = screen_baseline(screen_logs)

    days: list[ChainDay] = []
    d = start
    while d <= end:
        habits_state, ratio, defaulted = habit_day(habits, by_habit, d)
        sleep_log, screen_log = sleep_by.get(d), screen_by.get(d)
        study_mins = (study_by_day or {}).get(d, 0)
        urge_outs = (urge_by_day or {}).get(d, [])
        days.append(ChainDay(
            day=d, habits=habits_state, sleep=sleep_state(sleep_log),
            screen_time=screen_state(screen_log.total_minutes if screen_log else None, baseline),
            study=study_state(study_mins),
            urges=urge_state(urge_outs),
            habit_ratio=ratio,
            sleep_minutes=sleep_log.duration_minutes if sleep_log else None,
            screen_minutes=screen_log.total_minutes if screen_log else None,
            sleep_defaulted=bool(sleep_log and sleep_log.is_default),
            screen_time_defaulted=bool(screen_log and screen_log.is_default),
            habits_defaulted=defaulted,
        ))
        d += timedelta(days=1)
    return days
