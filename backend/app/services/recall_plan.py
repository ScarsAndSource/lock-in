"""
Exam radar scheduling. PURE.

This is NOT a study helper. The person lists the subject and the topic NAMES that will come in the exam; the app
brings that list back at +1, +3, +7 and +14 days ("a quick look"). The plan bends around everything else:
  - never on a blocked day (easy week, a pause, any exam day),
  - never after the exam (steps squeeze up to the day before it, extra steps are dropped),
  - at most MAX_PER_DAY reviews on one day across all subjects,
  - missed reviews are RESCHEDULED forward, never shown as overdue.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from uuid import UUID

from app.exceptions import ValidationError

STEPS = (1, 3, 7, 14)
MAX_PER_DAY = 2
SEARCH_DAYS = 14
MAX_TOPICS = 20
MAX_TOPIC_LEN = 60


def parse_topics(raw: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for part in re.split(r"[,\n;•]", raw or ""):
        t = " ".join(part.replace("<", "").replace(">", "").split()).lstrip("-*· ").strip()
        if not t:
            continue
        t = t[:MAX_TOPIC_LEN]
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    if not out:
        raise ValidationError("Add at least one topic or subject name.")
    return out[:MAX_TOPICS]


def merge_topics(existing: list[str], extra: list[str]) -> list[str]:
    seen = {t.lower() for t in existing}
    merged = list(existing)
    for t in extra:
        if t.lower() not in seen:
            seen.add(t.lower())
            merged.append(t)
    return merged[:MAX_TOPICS]


def _free(day: date, blocked, load: dict[date, int]) -> bool:
    return day not in blocked and load.get(day, 0) < MAX_PER_DAY


def place(target: date, lo: date, hi: date, blocked, load: dict[date, int]) -> date | None:
    """First free day in [target, hi]; else the latest free day in [lo, target); else None."""
    start = max(target, lo)
    d = start
    while d <= hi:
        if _free(d, blocked, load):
            return d
        d += timedelta(days=1)
    d = min(start, hi + timedelta(days=1)) - timedelta(days=1)
    while d >= lo:
        if _free(d, blocked, load):
            return d
        d -= timedelta(days=1)
    return None


def build_plan(start: date, exam: date | None, blocked, load: dict[date, int]) -> list[tuple[int, date]]:
    """[(step, due_date)] for a new set. MUTATES `load` so several sets planned in a row share the daily cap."""
    out: list[tuple[int, date]] = []
    last = start
    for step in STEPS:
        target = start + timedelta(days=step)
        if exam is not None and target >= exam:
            target = exam - timedelta(days=1)
        hi = exam - timedelta(days=1) if exam is not None else target + timedelta(days=SEARCH_DAYS)
        lo = last + timedelta(days=1)
        day = place(target, lo, hi, blocked, load)
        if day is None:
            continue
        out.append((step, day))
        load[day] = load.get(day, 0) + 1
        last = day
    return out


def reflow(
    pending: list[tuple[UUID, date, date | None]], today: date, blocked, load: dict[date, int],
) -> dict[UUID, date | None]:
    """
    pending = [(review_id, due_date, exam_date)]. `load` must count only the reviews that are NOT moving.
    Returns {review_id: new_due | None} for every review that is overdue or sits on a blocked day (None = drop it,
    it no longer fits before the exam). MUTATES `load`.
    """
    moves: dict[UUID, date | None] = {}
    for rid, due, exam in sorted(pending, key=lambda p: p[1]):
        if due >= today and due not in blocked:
            continue
        hi = exam - timedelta(days=1) if exam is not None else today + timedelta(days=SEARCH_DAYS)
        day = place(max(today, due), today, hi, blocked, load)
        moves[rid] = day
        if day is not None:
            load[day] = load.get(day, 0) + 1
    return moves