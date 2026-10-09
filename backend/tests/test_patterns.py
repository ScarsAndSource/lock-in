"""Unit tests for cross-domain pattern detection engine."""
from datetime import date, timedelta

from app.services.chain_service import BAD, GOOD, NONE, ChainDay
from app.services.pattern_service import find_patterns


def _chain_day(d: date, habits="good", sleep="good", screen_time="good",
               sleep_defaulted=False, screen_time_defaulted=False, habits_defaulted=False):
    return ChainDay(
        day=d, habits=habits, sleep=sleep, screen_time=screen_time,
        habit_ratio=1.0 if habits == "good" else 0.0 if habits == "bad" else None,
        sleep_minutes=480 if sleep == "good" else 300 if sleep == "bad" else None,
        screen_minutes=60 if screen_time == "good" else 300 if screen_time == "bad" else None,
        sleep_defaulted=sleep_defaulted, screen_time_defaulted=screen_time_defaulted,
        habits_defaulted=habits_defaulted,
    )


def test_patterns_detects_sleep_to_habits_correlation():
    # 5 days: bad sleep -> bad habits (rate 1.0)
    # 5 days: good sleep -> good habits (baseline rate 0.0)
    start = date(2026, 9, 1)
    days = []
    for i in range(5):
        days.append(_chain_day(start + timedelta(days=i), habits=BAD, sleep=BAD))
    for i in range(5, 10):
        days.append(_chain_day(start + timedelta(days=i), habits=GOOD, sleep=GOOD))

    patterns = find_patterns(days)
    assert any(p.key == "sleep->habits" for p in patterns)
    p = next(p for p in patterns if p.key == "sleep->habits")
    assert p.trigger_days == 5
    assert p.hits == 5
    assert p.rate_after_trigger == 1.0
    assert p.baseline_rate == 0.0
    assert len(p.evidence_dates) == 5


def test_patterns_detects_screen_time_to_habits_with_lag_1():
    # Day N heavy screen -> Day N+1 bad habits
    start = date(2026, 9, 1)
    days = []
    # 4 pairs of (heavy screen day, bad habit next day)
    for i in range(0, 8, 2):
        days.append(_chain_day(start + timedelta(days=i), screen_time=BAD, habits=GOOD))
        days.append(_chain_day(start + timedelta(days=i + 1), screen_time=GOOD, habits=BAD))
    # 4 baseline days where screen was good and habit stayed good
    for i in range(8, 12):
        days.append(_chain_day(start + timedelta(days=i), screen_time=GOOD, habits=GOOD))

    patterns = find_patterns(days)
    assert any(p.key == "screen_time->habits" for p in patterns)
    p = next(p for p in patterns if p.key == "screen_time->habits")
    assert p.lag_days == 1
    assert p.hits >= 3


def test_patterns_ignores_autofilled_default_days():
    # 4 days of bad sleep -> bad habits, but sleep was an auto-filled default
    start = date(2026, 9, 1)
    days = []
    for i in range(4):
        days.append(_chain_day(start + timedelta(days=i), habits=BAD, sleep=BAD, sleep_defaulted=True))
    for i in range(4, 10):
        days.append(_chain_day(start + timedelta(days=i), habits=GOOD, sleep=GOOD))

    patterns = find_patterns(days)
    # Defaulted days must not be usable as trigger evidence
    assert not any(p.key == "sleep->habits" for p in patterns)


def test_patterns_insufficient_trigger_days_returns_empty():
    start = date(2026, 9, 1)
    days = [
        _chain_day(start, habits=BAD, sleep=BAD),
        _chain_day(start + timedelta(days=1), habits=BAD, sleep=BAD),  # only 2 trigger days (< 3)
        _chain_day(start + timedelta(days=2), habits=GOOD, sleep=GOOD),
        _chain_day(start + timedelta(days=3), habits=GOOD, sleep=GOOD),
        _chain_day(start + timedelta(days=4), habits=GOOD, sleep=GOOD),
    ]
    patterns = find_patterns(days)
    assert patterns == []


def test_patterns_small_gap_over_baseline_is_not_reported():
    # If habits slip equally often without bad sleep, no causal pattern is reported
    start = date(2026, 9, 1)
    days = []
    for i in range(4):
        days.append(_chain_day(start + timedelta(days=i), habits=BAD, sleep=BAD))
    for i in range(4, 8):
        days.append(_chain_day(start + timedelta(days=i), habits=BAD, sleep=GOOD))  # also bad habits!

    patterns = find_patterns(days)
    assert not any(p.key == "sleep->habits" for p in patterns)
