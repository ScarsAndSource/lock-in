"""Graduation rules. PURE. The app OFFERS; the person decides. Retired habits get check-ins at +30 and +90 days."""
from __future__ import annotations

from datetime import date, timedelta

WINDOW_DAYS = 56
MIN_EXPECTED = 20
MIN_PCT = 80.0
MIN_AGE_DAYS = 56
MIN_AUTOMATIC = 6          # only applied when the person has taken a snapshot
MAX_OFFERS = 2


def offer(consistency_pct: float | None, expected: int, habit_age_days: int, latest_automatic: int | None) -> bool:
    if consistency_pct is None or expected < MIN_EXPECTED or habit_age_days < MIN_AGE_DAYS:
        return False
    if consistency_pct < MIN_PCT:
        return False
    return latest_automatic is None or latest_automatic >= MIN_AUTOMATIC


def check_dates(on: date) -> tuple[date, date]:
    return on + timedelta(days=30), on + timedelta(days=90)


def due_check(
    check30_on: date, check90_on: date, check30_result: str | None, check90_result: str | None, today: date,
) -> int | None:
    """Which check-in (30 or 90) is waiting, if any. A missed 30 is skipped once the 90 is reachable."""
    if today >= check90_on and check90_result is None:
        return 90
    if today >= check30_on and check30_result is None and today < check90_on:
        return 30
    return None
