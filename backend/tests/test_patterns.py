from datetime import date, datetime, timezone
from uuid import uuid4

from app.domain import HabitDefinition, HabitLog, HabitStatus, TargetFrequency
from app.services.pattern_service import detect_habit_patterns

USER = uuid4()


def _habit():
    return HabitDefinition(
        id=uuid4(), user_id=USER, name="H", target_frequency=TargetFrequency(type="n_per_week", count=3),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _log(habit, d, status=HabitStatus.DONE):
    return HabitLog(habit_id=habit.id, user_id=USER, log_date=d, status=status)


def test_day_of_week_preference_detected_with_high_confidence():
    habit = _habit()
    # Always trains on Monday/Wednesday/Friday for 8 weeks
    logs = []
    for w in range(8):
        base = date(2026, 7, 6) + __import__("datetime").timedelta(weeks=w)  # Jul 6 = Monday
        logs += [_log(habit, base), _log(habit, base + __import__("datetime").timedelta(2)),
                 _log(habit, base + __import__("datetime").timedelta(4))]

    result = detect_habit_patterns(habit, logs, as_of=date(2026, 9, 6))
    pattern_types = {p.pattern_type for p in result}
    assert "preferred_days" in pattern_types
    pref = next(p for p in result if p.pattern_type == "preferred_days")
    assert set(pref.details["days"]) == {0, 2, 4}
    assert pref.confidence >= 0.8


def test_weekend_warrior_detected():
    habit = _habit()
    import datetime as dt
    logs = []
    for w in range(6):
        base = date(2026, 7, 6) + dt.timedelta(weeks=w)
        sat = base + dt.timedelta(5)
        sun = base + dt.timedelta(6)
        logs += [_log(habit, sat), _log(habit, sun)]

    result = detect_habit_patterns(habit, logs, as_of=date(2026, 8, 22))
    pattern_types = {p.pattern_type for p in result}
    assert "weekend_warrior" in pattern_types


def test_low_data_returns_no_patterns():
    habit = _habit()
    logs = [_log(habit, date(2026, 9, 1))]
    result = detect_habit_patterns(habit, logs, as_of=date(2026, 9, 7))
    assert result == []


def test_all_same_day_is_preferred_day_and_not_weekend_warrior():
    habit = _habit()
    import datetime as dt
    logs = [_log(habit, date(2026, 7, 6) + dt.timedelta(weeks=w)) for w in range(8)]  # all Mondays
    result = detect_habit_patterns(habit, logs, as_of=date(2026, 9, 6))
    assert any(p.pattern_type == "preferred_days" for p in result)
    assert not any(p.pattern_type == "weekend_warrior" for p in result)
