"""
Seasons: 6 focus weeks + 1 easy week (49 days), at most 3 focus habits. PURE.

A season never expires on its own and nothing is ever deleted: when the 7 weeks are over the phase reads "ended"
and the app invites the next season. Habits outside the focus list are BENCHED (still loggable, just quiet).
Accounts that already have more than 3 habits get slots = their count, so the cap only ever stops NEW ones.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from app.exceptions import ValidationError

FOCUS_DAYS = 42
SEASON_DAYS = 49
DEFAULT_SLOTS = 3
MAX_SLOTS = 50
MAX_NAME_LEN = 60


@dataclass(frozen=True, slots=True)
class Phase:
    kind: Literal["focus", "rest", "ended"]
    week: int          # 1-6 focus, 7 rest/ended
    days_left: int     # days left in the current block (0 once ended)


def phase(start: date, today: date) -> Phase:
    d = max(0, (today - start).days)
    if d < FOCUS_DAYS:
        return Phase("focus", d // 7 + 1, FOCUS_DAYS - d)
    if d < SEASON_DAYS:
        return Phase("rest", 7, SEASON_DAYS - d)
    return Phase("ended", 7, 0)


def rest_days(start: date) -> frozenset[date]:
    return frozenset(start + timedelta(days=i) for i in range(FOCUS_DAYS, SEASON_DAYS))


def slots_for(active_count: int) -> int:
    return max(DEFAULT_SLOTS, min(active_count, MAX_SLOTS))


def live_focus(focus_ids, active_ids) -> list[UUID]:
    """Focus habits that are still active, in order (archived/graduated ones free their slot)."""
    active = set(active_ids)
    return [h for h in focus_ids if h in active]


def free_slots(slots: int, focus_ids, active_ids) -> int:
    return max(0, slots - len(live_focus(focus_ids, active_ids)))


def validate_focus(ids, slots: int, active_ids) -> list[UUID]:
    active = set(active_ids)
    seen: list[UUID] = []
    for h in ids:
        if h not in active:
            raise ValidationError("You can only focus on habits that are active.")
        if h not in seen:
            seen.append(h)
    if len(seen) > slots:
        raise ValidationError(f"Pick at most {slots} focus habits.")
    return seen


def clean_name(raw: str | None, fallback: str) -> str:
    name = " ".join((raw or "").replace("<", "").replace(">", "").split())
    if not name:
        return fallback
    return name[:MAX_NAME_LEN]


def not_yet_message(names: list[str]) -> str:
    shown = ", ".join(names[:3]) if names else "your focus habits"
    return f"Not yet. Finish these first: {shown}. Graduate or let one go to make room."