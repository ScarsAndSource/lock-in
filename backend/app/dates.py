"""Time helpers. All 'now' comes through an injectable Clock so tests are deterministic."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.exceptions import ValidationError

Clock = Callable[[], datetime]

MAX_BACKFILL_DAYS = 400


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ValidationError(f"Unknown timezone: {name!r}. Use an IANA name like 'Asia/Kolkata'.") from exc
    return name


def user_today(tz_name: str, clock: Clock = utc_now) -> date:
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        tz = ZoneInfo("UTC")
    return clock().astimezone(tz).date()


def assert_loggable_date(target: date, utc_today: date) -> None:
    """
    Rejects dates in the future and absurdly old backfills. Bound is
    utc_today + 1 day because the furthest-ahead timezone (UTC+14) is at most
    one calendar day ahead of UTC -- so no profile lookup is needed and no
    legitimate user is ever rejected for being "ahead".
    """
    if target > utc_today + timedelta(days=1):
        raise ValidationError("Can't log a date in the future.")
    if (utc_today - target).days > MAX_BACKFILL_DAYS:
        raise ValidationError(f"Can't backfill more than {MAX_BACKFILL_DAYS} days.")
