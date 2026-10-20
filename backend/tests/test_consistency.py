from datetime import date, datetime, timezone
from uuid import uuid4

from app.domain import HabitDefinition, HabitLog, HabitStatus, TargetFrequency
from app.services.consistency_service import compute_habit_consistency, overall_consistency

USER = uuid4()


def _habit(freq):
    return HabitDefinition(
        id=uuid4(), user_id=USER, name="H", target_frequency=freq,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _log(habit, d, status=HabitStatus.DONE):
    return HabitLog(habit_id=habit.id, user_id=USER, log_date=d, status=status)


def test_weekday_habit_percentage_runs_and_comeback():
    habit = _habit(TargetFrequency(type="weekdays", days=(0, 2, 4)))  # Mon/Wed/Fri
    logs = [
        _log(habit, date(2026, 9, 14)), _log(habit, date(2026, 9, 16)),
        _log(habit, date(2026, 9, 18), HabitStatus.SKIPPED),
        _log(habit, date(2026, 9, 21)), _log(habit, date(2026, 9, 23), HabitStatus.PARTIAL),
        _log(habit, date(2026, 9, 25)),
    ]
    r = compute_habit_consistency(habit, logs, end_date=date(2026, 9, 27), window_days=14)
    assert r.consistency_pct == 75.0          # (1+1+0+1+0.5+1) / 6
    assert r.longest_run == 3 and r.current_run == 3 and r.run_unit == "days"
    assert r.comeback_rate == 100.0           # the one miss was followed by a non-miss
    assert r.coverage_pct == 100.0


def test_todays_unlogged_scheduled_day_is_pending_not_a_miss():
    habit = _habit(TargetFrequency(type="weekdays", days=(0, 2)))  # Mon/Wed
    logs = [_log(habit, date(2026, 9, 21))]
    r = compute_habit_consistency(habit, logs, end_date=date(2026, 9, 23), window_days=3)  # Wed pending
    assert r.expected == 1.0
    assert r.consistency_pct == 100.0


def test_no_scheduled_days_in_window_gives_none_not_zero():
    habit = _habit(TargetFrequency(type="weekdays", days=(0,)))
    r = compute_habit_consistency(habit, [], end_date=date(2026, 9, 29), window_days=1)  # a Tuesday
    assert r.consistency_pct is None


def test_n_per_week_caps_at_100_and_counts_weekly_runs():
    habit = _habit(TargetFrequency(type="n_per_week", count=3))
    logs = [_log(habit, date(2026, 9, d)) for d in (21, 22, 23, 24, 25)]  # 5 done, target 3
    r = compute_habit_consistency(habit, logs, end_date=date(2026, 9, 27), window_days=7)
    assert r.consistency_pct == 100.0
    assert r.longest_run == 1 and r.run_unit == "weeks"


def test_overall_is_the_mean_of_habit_percentages():
    full, empty = _habit(TargetFrequency(type="n_per_week", count=3)), _habit(TargetFrequency(type="n_per_week", count=3))
    logs = [_log(full, date(2026, 9, d)) for d in (21, 22, 23)]
    items = [compute_habit_consistency(h, logs, date(2026, 9, 27), 7) for h in (full, empty)]
    assert overall_consistency(items) == 50.0


def test_auto_filled_default_logs_do_not_count_toward_consistency():
    habit = _habit(TargetFrequency(type="weekdays", days=(0, 2, 4)))
    # Logs are present but flagged as auto-filled guesses (is_default=True)
    logs = [
        HabitLog(habit_id=habit.id, user_id=USER, log_date=date(2026, 9, 21), status=HabitStatus.DONE, is_default=True),
        HabitLog(habit_id=habit.id, user_id=USER, log_date=date(2026, 9, 23), status=HabitStatus.DONE, is_default=True),
    ]
    r = compute_habit_consistency(habit, logs, end_date=date(2026, 9, 25), window_days=7)
    # Defaulted logs earn 0 credit; earned should be 0.0, consistency_pct 0.0
    assert r.earned == 0.0
    assert r.consistency_pct == 0.0
    assert r.logged_days == 0


def test_new_habit_is_only_judged_from_its_first_day():
    habit = _habit(TargetFrequency(type="weekdays", days=(0, 1, 2, 3, 4, 5, 6)))
    today = date(2026, 9, 27)
    logs = [_log(habit, today)]
    before = compute_habit_consistency(habit, logs, end_date=today, window_days=30)
    assert before.consistency_pct == 3.3          # the old bug: 29 days before it existed counted as misses
    after = compute_habit_consistency(habit, logs, end_date=today, window_days=30, habit_start=today)
    assert after.consistency_pct == 100.0 and after.expected == 1.0 and after.coverage_pct == 100.0


def test_new_n_per_week_habit_is_not_scored_against_older_days():
    habit = _habit(TargetFrequency(type="n_per_week", count=3))
    today = date(2026, 9, 27)
    logs = [_log(habit, today)]
    r = compute_habit_consistency(habit, logs, end_date=today, window_days=30, habit_start=today)
    assert r.consistency_pct == 100.0 and r.coverage_pct == 100.0


def test_backfilled_logs_before_creation_still_count():
    habit = _habit(TargetFrequency(type="weekdays", days=(0, 1, 2, 3, 4, 5, 6)))
    logs = [_log(habit, date(2026, 9, 25)), _log(habit, date(2026, 9, 26)), _log(habit, date(2026, 9, 27))]
    r = compute_habit_consistency(habit, logs, end_date=date(2026, 9, 27), window_days=30, habit_start=date(2026, 9, 27))
    assert r.expected == 3.0 and r.consistency_pct == 100.0
