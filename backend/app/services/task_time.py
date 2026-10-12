"""
Local-time helpers for tasks. Pure: no DB, no clock, no model.

The wire format for "when" (from the API AND from the AI capture step) is a LOCAL string in the person's
own timezone: "YYYY-MM-DD" (a day, no clock time) or "YYYY-MM-DDTHH:MM". One parser for both, so the model's
output and a form submission are validated by exactly the same rules.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.exceptions import ValidationError

_LOCAL_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?$")
END_OF_DAY = time(23, 59)


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo("UTC")


def parse_local(value: str, tz: ZoneInfo) -> tuple[datetime, bool]:
    """-> (aware datetime in tz, has_time). A bare date becomes 23:59 local with has_time=False."""
    m = _LOCAL_RE.match((value or "").strip())
    if not m:
        raise ValidationError("Use YYYY-MM-DD or YYYY-MM-DDTHH:MM (your local time).")
    y, mo, d, hh, mm = m.groups()
    try:
        if hh is None:
            return datetime(int(y), int(mo), int(d), END_OF_DAY.hour, END_OF_DAY.minute, tzinfo=tz), False
        return datetime(int(y), int(mo), int(d), int(hh), int(mm), tzinfo=tz), True
    except ValueError as exc:
        raise ValidationError(f"{value!r} is not a real date/time.") from exc


def format_local(dt: datetime | None, has_time: bool, tz: ZoneInfo) -> str | None:
    if dt is None:
        return None
    local = dt.astimezone(tz)
    return local.strftime("%Y-%m-%dT%H:%M") if has_time else local.strftime("%Y-%m-%d")


def clock_label(dt: datetime, tz: ZoneInfo) -> str:
    """'6:30 PM' -- no platform-specific strftime flags."""
    local = dt.astimezone(tz)
    hour12 = local.hour % 12 or 12
    return f"{hour12}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def at_local(day: date, clock: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, clock, tzinfo=tz)


def check_window(dt: datetime, now: datetime, *, max_past_days: int, max_future_days: int = 730) -> bool:
    """True when dt is sane: not absurdly old, not absurdly far out."""
    return now - timedelta(days=max_past_days) <= dt <= now + timedelta(days=max_future_days)


def next_occurrence(
    *, done_at: datetime, repeat_days: int, due_at: datetime | None, due_has_time: bool,
    remind_at: datetime | None, tz: ZoneInfo,
) -> tuple[datetime | None, bool, datetime | None]:
    """
    A cadence task comes due again `repeat_days` after it was COMPLETED (late is fine; it never piles up).
    Keeps the clock time of the old due (or the old reminder when there was no due), and the old
    reminder-before-due offset. A reminder-only task stays reminder-only.
    -> (next_due | None, due_has_time, next_remind | None)
    """
    done_day = done_at.astimezone(tz).date()
    next_day = done_day + timedelta(days=repeat_days)
    if due_at is not None:
        clock = due_at.astimezone(tz).timetz().replace(tzinfo=None) if due_has_time else END_OF_DAY
        next_due = at_local(next_day, clock, tz)
        next_remind = None
        if remind_at is not None:
            offset = due_at - remind_at
            next_remind = next_due - offset if offset >= timedelta(0) else at_local(
                next_day, remind_at.astimezone(tz).timetz().replace(tzinfo=None), tz
            )
        return next_due, due_has_time, next_remind
    if remind_at is not None:
        r_clock = remind_at.astimezone(tz).timetz().replace(tzinfo=None)
        return None, True, at_local(next_day, r_clock, tz)
    return at_local(next_day, END_OF_DAY, tz), False, None


def utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)
