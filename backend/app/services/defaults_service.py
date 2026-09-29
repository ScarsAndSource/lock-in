"""
Computes "same as usual" defaults for the opt-out daily check-in
(SPEC.md section 10, item 1).

Design, stated explicitly because SPEC.md does not pin down an exact
algorithm and this is a genuine engineering decision, not a detail:

For a given habit and target date, look at the habit's logged history on
the SAME weekday (a gym habit skipped every Sunday and done every other
day has a real weekday pattern; collapsing all days together would wash
that out). Take up to the last 4 same-weekday occurrences:

  - 2+ prior occurrences on that weekday: default = the majority status
    among them. A tie goes to the most recent one (recency beats a stale
    tie). This is treated as a confident default.
  - 0 or 1 prior occurrences: not enough signal to call this "usual" yet.
    Default optimistically to DONE (the habit exists because the user
    declared an intention to do it), but flagged is_low_confidence=True so
    the UI can visually distinguish a real pattern from a first guess
    instead of presenting both with equal confidence.

This function is pure: no I/O, no clock access beyond the target_date
argument, fully deterministic given its inputs. Whether a habit already
has a real log for target_date, and therefore shouldn't get a default
proposed at all, is the caller's responsibility (checkins_service) — this
function always proposes a default for every habit it's given, on the
assumption that filtering already happened upstream.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from uuid import UUID

from app.domain import HabitDefault, HabitDefinition, HabitLog, HabitStatus

_LOOKBACK_OCCURRENCES = 4
_MIN_OCCURRENCES_FOR_CONFIDENCE = 2


def compute_habit_defaults(
    habits: list[HabitDefinition],
    logs_by_habit: dict[UUID, list[HabitLog]],
    target_date: date,
) -> dict[UUID, HabitDefault]:
    """
    habits: active habit definitions to compute a default for.
    logs_by_habit: each habit's log history (any order, any date range —
        this function does the filtering and sorting itself). Habits with
        no entry in this dict are treated as having no history.
    target_date: the date the default is being proposed for.

    Returns a dict keyed by habit_id. Every habit passed in gets an entry —
    there is no silent skipping, since a caller that passed a habit in
    clearly wants a default for it.
    """
    results: dict[UUID, HabitDefault] = {}

    for habit in habits:
        history = logs_by_habit.get(habit.id, [])
        results[habit.id] = _compute_single_default(habit, history, target_date)

    return results


def _compute_single_default(
    habit: HabitDefinition,
    history: list[HabitLog],
    target_date: date,
) -> HabitDefault:
    same_weekday_logs = sorted(
        (log for log in history if log.log_date.weekday() == target_date.weekday()
         and log.log_date < target_date),
        key=lambda log: log.log_date,
        reverse=True,
    )[:_LOOKBACK_OCCURRENCES]

    occurrence_count = len(same_weekday_logs)

    if occurrence_count < _MIN_OCCURRENCES_FOR_CONFIDENCE:
        return HabitDefault(
            habit_id=habit.id,
            status=HabitStatus.DONE,
            is_low_confidence=True,
            based_on_count=occurrence_count,
            reason=(
                "Not enough history on this weekday yet — defaulting to "
                "done since that's the habit's stated goal."
            ),
        )

    status_counts = Counter(log.status for log in same_weekday_logs)
    top_count = max(status_counts.values())
    tied_statuses = [s for s, c in status_counts.items() if c == top_count]

    if len(tied_statuses) == 1:
        chosen_status = tied_statuses[0]
    else:
        # Tie: recency wins. same_weekday_logs is already sorted most
        # recent first, so the first log whose status is in the tie set
        # is the tiebreaker.
        chosen_status = next(
            log.status for log in same_weekday_logs if log.status in tied_statuses
        )

    return HabitDefault(
        habit_id=habit.id,
        status=chosen_status,
        is_low_confidence=False,
        based_on_count=occurrence_count,
        reason=(
            f"Usually '{chosen_status.value}' on this day of the week "
            f"({top_count}/{occurrence_count} of the last {occurrence_count} "
            f"occurrences)."
        ),
    )
