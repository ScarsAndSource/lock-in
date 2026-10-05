from datetime import date, datetime, time, timezone
from uuid import uuid4

from app.domain import HabitDefinition, HabitLog, HabitStatus, ScreenTimeLog, ScreenTimeSource, SleepLog, TargetFrequency
from app.services.defaults_service import compute_habit_defaults, compute_screen_time_default, compute_sleep_default

USER = uuid4()
THURSDAY = date(2026, 9, 24)
assert THURSDAY.weekday() == 3


def _habit(freq):
    return HabitDefinition(
        id=uuid4(), user_id=USER, name="Gym", target_frequency=freq,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _log(habit, d, status):
    return HabitLog(habit_id=habit.id, user_id=USER, log_date=d, status=status)


def _default(habit, logs, target=THURSDAY):
    return compute_habit_defaults([habit], {habit.id: logs}, target)[habit.id]


def test_weekday_habit_on_an_off_day_proposes_nothing():
    habit = _habit(TargetFrequency(type="weekdays", days=(0, 2, 4)))  # Mon/Wed/Fri
    result = _default(habit, [])
    assert result.is_scheduled is False
    assert result.status is None


def test_weekday_habit_on_a_scheduled_day_still_defaults():
    habit = _habit(TargetFrequency(type="weekdays", days=(0, 2, 4)))
    result = _default(habit, [], target=date(2026, 9, 23))  # Wednesday
    assert result.is_scheduled is True
    assert result.status == HabitStatus.DONE


def test_weekly_quota_met_means_rest_for_the_rest_of_the_week():
    habit = _habit(TargetFrequency(type="n_per_week", count=2))
    logs = [_log(habit, date(2026, 9, 21), HabitStatus.DONE), _log(habit, date(2026, 9, 22), HabitStatus.DONE)]
    result = _default(habit, logs)
    assert result.is_scheduled is False
    assert "already met" in result.reason


def test_partial_counts_half_toward_the_weekly_quota():
    habit = _habit(TargetFrequency(type="n_per_week", count=2))
    logs = [_log(habit, date(2026, 9, 21), HabitStatus.DONE), _log(habit, date(2026, 9, 22), HabitStatus.PARTIAL)]
    assert _default(habit, logs).is_scheduled is True  # 1.5 < 2


def test_last_weeks_logs_do_not_count_toward_this_weeks_quota():
    habit = _habit(TargetFrequency(type="n_per_week", count=2))
    logs = [_log(habit, date(2026, 9, 14), HabitStatus.DONE), _log(habit, date(2026, 9, 15), HabitStatus.DONE)]
    assert _default(habit, logs).is_scheduled is True


def _sleep(d, bed, wake, quality, is_default=False):
    return SleepLog(user_id=USER, log_date=d, time_to_bed=bed, time_woke=wake,
                    self_rated_quality=quality, is_default=is_default)


def test_sleep_default_uses_circular_median_for_bedtime():
    history = [
        _sleep(date(2026, 9, 20), time(23, 30), time(7, 0), 4),
        _sleep(date(2026, 9, 21), time(0, 30), time(7, 0), 4),
    ]
    proposal = compute_sleep_default(history, THURSDAY)
    assert proposal.time_to_bed == time(0, 0)  # NOT 12:00
    assert proposal.time_woke == time(7, 0)
    assert proposal.self_rated_quality == 4
    assert proposal.is_low_confidence is True  # only 2 nights


def test_sleep_default_needs_two_real_logs_and_ignores_auto_filled_ones():
    one_real = [_sleep(date(2026, 9, 20), time(23, 0), time(7, 0), 4)]
    assert compute_sleep_default(one_real, THURSDAY) is None
    all_defaults = [_sleep(date(2026, 9, d), time(23, 0), time(7, 0), 4, is_default=True) for d in (20, 21, 22)]
    assert compute_sleep_default(all_defaults, THURSDAY) is None


def test_screen_time_default_is_the_median_of_real_logs():
    history = [
        ScreenTimeLog(user_id=USER, log_date=date(2026, 9, d), total_minutes=m, source=ScreenTimeSource.MANUAL)
        for d, m in ((20, 100), (21, 200), (22, 300))
    ]
    proposal = compute_screen_time_default(history, THURSDAY)
    assert proposal.total_minutes == 200
    assert proposal.is_low_confidence is True
