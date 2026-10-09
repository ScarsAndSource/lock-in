"""
"Same as usual" defaults for the opt-out daily check-in.

HABITS: same-weekday history of REAL logs (is_default rows excluded so
guesses never count as evidence or feed on themselves), last 4 occurrences,
majority wins, tie -> most recent; <2 occurrences -> optimistic DONE flagged
low-confidence. Rest days (see schedule.py) propose nothing.

SLEEP / SCREEN TIME: median of the last 7 REAL logs. Auto-filled (is_default)
rows are excluded from the basis so a guess can never feed on itself and turn
into fabricated "history". Needs >= 2 real logs, else no proposal.
Bedtime uses a circular median (23:30 & 00:30 -> 00:00, not 12:00).

All functions are pure.
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import date, time
from uuid import UUID

from app.domain import (
    HabitDefault, HabitDefinition, HabitLog, HabitStatus,
    ScreenTimeLog, ScreenTimeProposal, SleepLog, SleepProposal,
)
from app.services.schedule import check_scheduled

_LOOKBACK_OCCURRENCES = 4
_MIN_OCCURRENCES_FOR_CONFIDENCE = 2

_PROPOSAL_WINDOW = 7
_PROPOSAL_MIN_LOGS = 2
_PROPOSAL_CONFIDENT_LOGS = 4
_BEDTIME_OFFSET = 18 * 60  # minutes after 18:00 -> midnight is mid-scale, not a cliff


# ------------------------------------------------------------------ habits
def compute_habit_defaults(
    habits: list[HabitDefinition],
    logs_by_habit: dict[UUID, list[HabitLog]],
    target_date: date,
) -> dict[UUID, HabitDefault]:
    return {
        habit.id: _compute_single_default(habit, logs_by_habit.get(habit.id, []), target_date)
        for habit in habits
    }


def _compute_single_default(habit: HabitDefinition, history: list[HabitLog], target_date: date) -> HabitDefault:
    verdict = check_scheduled(habit.target_frequency, target_date, history)
    if not verdict.scheduled:
        return HabitDefault(
            habit_id=habit.id, status=None, is_low_confidence=False,
            based_on_count=0, reason=verdict.reason, is_scheduled=False,
        )

    same_weekday_logs = sorted(
        (log for log in history if not log.is_default and log.log_date.weekday() == target_date.weekday() and log.log_date < target_date),
        key=lambda log: log.log_date,
        reverse=True,
    )[:_LOOKBACK_OCCURRENCES]
    occurrence_count = len(same_weekday_logs)

    if occurrence_count < _MIN_OCCURRENCES_FOR_CONFIDENCE:
        return HabitDefault(
            habit_id=habit.id, status=HabitStatus.DONE, is_low_confidence=True,
            based_on_count=occurrence_count,
            reason="Not enough history on this weekday yet — defaulting to done since that's the habit's stated goal.",
        )

    status_counts = Counter(log.status for log in same_weekday_logs)
    top_count = max(status_counts.values())
    tied = [s for s, c in status_counts.items() if c == top_count]
    chosen = tied[0] if len(tied) == 1 else next(log.status for log in same_weekday_logs if log.status in tied)

    return HabitDefault(
        habit_id=habit.id, status=chosen, is_low_confidence=False, based_on_count=occurrence_count,
        reason=(
            f"Usually '{chosen.value}' on this day of the week "
            f"({top_count}/{occurrence_count} of the last {occurrence_count} occurrences)."
        ),
    )


# ------------------------------------------------------------------ sleep / screen
def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _to_time(total_minutes: int) -> time:
    total_minutes %= 24 * 60
    return time(total_minutes // 60, total_minutes % 60)


def _median_bedtime(bed_minutes: list[int]) -> time:
    shifted = [(m - _BEDTIME_OFFSET) % (24 * 60) for m in bed_minutes]
    median = round(statistics.median(shifted))
    return _to_time(median + _BEDTIME_OFFSET)


def _median_clock(minutes: list[int]) -> time:
    return _to_time(round(statistics.median(minutes)))


def _recent_real(history, target_date: date) -> list:
    real = [log for log in history if not log.is_default and log.log_date < target_date]
    return sorted(real, key=lambda log: log.log_date, reverse=True)[:_PROPOSAL_WINDOW]


def compute_sleep_default(history: list[SleepLog], target_date: date) -> SleepProposal | None:
    real = _recent_real(history, target_date)
    if len(real) < _PROPOSAL_MIN_LOGS:
        return None

    beds = [_minutes(l.time_to_bed) for l in real if l.time_to_bed is not None]
    wakes = [_minutes(l.time_woke) for l in real if l.time_woke is not None]
    quals = [l.self_rated_quality for l in real if l.self_rated_quality is not None]

    bed = _median_bedtime(beds) if len(beds) >= 2 else None
    wake = _median_clock(wakes) if len(wakes) >= 2 else None
    quality = statistics.median_low(quals) if len(quals) >= 2 else None
    if bed is None and wake is None and quality is None:
        return None

    return SleepProposal(
        time_to_bed=bed, time_woke=wake, self_rated_quality=quality,
        based_on_count=len(real),
        is_low_confidence=len(real) < _PROPOSAL_CONFIDENT_LOGS,
        reason=f"Typical of your last {len(real)} logged nights.",
    )


def compute_screen_time_default(history: list[ScreenTimeLog], target_date: date) -> ScreenTimeProposal | None:
    real = _recent_real(history, target_date)
    if len(real) < _PROPOSAL_MIN_LOGS:
        return None
    minutes = int(round(statistics.median(l.total_minutes for l in real)))
    return ScreenTimeProposal(
        total_minutes=minutes, based_on_count=len(real),
        is_low_confidence=len(real) < _PROPOSAL_CONFIDENT_LOGS,
        reason=f"Typical of your last {len(real)} logged days.",
    )
