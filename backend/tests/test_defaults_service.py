from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from app.domain import (
    HabitDefinition,
    HabitLog,
    HabitStatus,
    TargetFrequency,
)
from app.services.defaults_service import compute_habit_defaults

USER_ID = uuid4()


def _habit(freq: TargetFrequency | None = None) -> HabitDefinition:
    return HabitDefinition(
        id=uuid4(),
        user_id=USER_ID,
        name="Gym",
        target_frequency=freq or TargetFrequency(type="n_per_week", count=5),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _log(habit_id, log_date: date, status: HabitStatus, is_default: bool = False) -> HabitLog:
    return HabitLog(habit_id=habit_id, user_id=USER_ID, log_date=log_date, status=status, is_default=is_default)


# Target date: Thursday, 2026-09-24 (weekday() == 3)
TARGET = date(2026, 9, 24)
assert TARGET.weekday() == 3


def test_new_habit_with_no_history_defaults_to_done_and_is_low_confidence():
    habit = _habit()
    result = compute_habit_defaults([habit], {}, TARGET)[habit.id]

    assert result.status == HabitStatus.DONE
    assert result.is_low_confidence is True
    assert result.based_on_count == 0


def test_single_prior_occurrence_is_still_low_confidence():
    habit = _habit()
    logs = [_log(habit.id, date(2026, 9, 17), HabitStatus.SKIPPED)]  # one prior Thursday

    result = compute_habit_defaults([habit], {habit.id: logs}, TARGET)[habit.id]

    assert result.is_low_confidence is True
    assert result.based_on_count == 1
    # Not enough signal to trust a single skip -- stays optimistic.
    assert result.status == HabitStatus.DONE


def test_consistent_history_produces_confident_matching_default():
    habit = _habit()
    logs = [
        _log(habit.id, date(2026, 9, 17), HabitStatus.DONE),
        _log(habit.id, date(2026, 9, 10), HabitStatus.DONE),
        _log(habit.id, date(2026, 9, 3), HabitStatus.DONE),
    ]

    result = compute_habit_defaults([habit], {habit.id: logs}, TARGET)[habit.id]

    assert result.status == HabitStatus.DONE
    assert result.is_low_confidence is False
    assert result.based_on_count == 3


def test_majority_wins_over_minority():
    habit = _habit()
    logs = [
        _log(habit.id, date(2026, 9, 17), HabitStatus.SKIPPED),
        _log(habit.id, date(2026, 9, 10), HabitStatus.SKIPPED),
        _log(habit.id, date(2026, 9, 3), HabitStatus.DONE),
    ]

    result = compute_habit_defaults([habit], {habit.id: logs}, TARGET)[habit.id]

    assert result.status == HabitStatus.SKIPPED
    assert result.is_low_confidence is False


def test_tie_breaks_toward_most_recent():
    habit = _habit()
    logs = [
        _log(habit.id, date(2026, 9, 17), HabitStatus.SKIPPED),  # most recent
        _log(habit.id, date(2026, 9, 10), HabitStatus.DONE),
    ]

    result = compute_habit_defaults([habit], {habit.id: logs}, TARGET)[habit.id]

    assert result.status == HabitStatus.SKIPPED  # the more recent of the tie


def test_only_last_four_same_weekday_occurrences_are_considered():
    habit = _habit()
    # 5 prior Thursdays: oldest two are DONE, most recent three are SKIPPED.
    logs = [
        _log(habit.id, date(2026, 9, 17), HabitStatus.SKIPPED),
        _log(habit.id, date(2026, 9, 10), HabitStatus.SKIPPED),
        _log(habit.id, date(2026, 9, 3), HabitStatus.SKIPPED),
        _log(habit.id, date(2026, 8, 27), HabitStatus.DONE),
        _log(habit.id, date(2026, 8, 20), HabitStatus.DONE),
    ]

    result = compute_habit_defaults([habit], {habit.id: logs}, TARGET)[habit.id]

    assert result.based_on_count == 4  # not 5
    assert result.status == HabitStatus.SKIPPED


def test_logs_on_other_weekdays_are_ignored():
    habit = _habit()
    logs = [
        _log(habit.id, date(2026, 9, 21), HabitStatus.DONE),  # Monday
        _log(habit.id, date(2026, 9, 25), HabitStatus.DONE),  # Friday
    ]

    result = compute_habit_defaults([habit], {habit.id: logs}, TARGET)[habit.id]

    assert result.based_on_count == 0
    assert result.is_low_confidence is True


def test_future_logs_relative_to_target_date_are_excluded():
    habit = _habit()
    logs = [_log(habit.id, date(2026, 10, 1), HabitStatus.SKIPPED)]  # a future Thursday

    result = compute_habit_defaults([habit], {habit.id: logs}, TARGET)[habit.id]

    assert result.based_on_count == 0


def test_no_habits_returns_empty_dict_without_error():
    assert compute_habit_defaults([], {}, TARGET) == {}


def test_multiple_habits_are_computed_independently():
    habit_a = _habit()
    habit_b = _habit()
    logs_a = [
        _log(habit_a.id, date(2026, 9, 17), HabitStatus.DONE),
        _log(habit_a.id, date(2026, 9, 10), HabitStatus.DONE),
    ]

    results = compute_habit_defaults([habit_a, habit_b], {habit_a.id: logs_a}, TARGET)

    assert results[habit_a.id].status == HabitStatus.DONE
    assert results[habit_a.id].is_low_confidence is False
    assert results[habit_b.id].is_low_confidence is True


def test_autofilled_defaults_are_excluded_from_history():
    """Auto-filled default logs must never count as evidence for future defaults."""
    habit = _habit()
    logs = [
        _log(habit.id, date(2026, 9, 17), HabitStatus.SKIPPED, is_default=True),
        _log(habit.id, date(2026, 9, 10), HabitStatus.SKIPPED, is_default=True),
    ]

    result = compute_habit_defaults([habit], {habit.id: logs}, TARGET)[habit.id]

    # Without real logs, defaults count as 0 occurrences
    assert result.based_on_count == 0
    assert result.is_low_confidence is True


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"type": "weekdays", "days": ()}, "weekdays frequency requires"),
        ({"type": "weekdays", "days": (7,)}, "0 \\(Mon\\) through 6"),
        ({"type": "n_per_week", "count": 0}, "count must be between"),
        ({"type": "n_per_week", "count": 8}, "count must be between"),
        ({"type": "biweekly"}, "unknown target_frequency type"),
    ],
)
def test_target_frequency_validates_its_shape(kwargs, message):
    with pytest.raises(ValueError, match=message):
        TargetFrequency(**kwargs)
