"""
Slow unlock. PURE and DERIVED: the stage is computed from account age + real check-ins every time, never stored,
so it can't desync. Fail-open everywhere: accounts older than UNLOCK_EPOCH start at the top stage (nobody loses a
feature), and the app treats any error as "show everything".

  0  one card + the check-in
  1  tasks + quick add + day orbit
  2  week weave, status chips, exam radar, journey nudges
  3  Growth and Journey sub-tabs, insights
  4  everything
"""
from __future__ import annotations

from datetime import date

# EDIT THIS to the day you ship the feature: accounts created before it are existing users and keep everything.
UNLOCK_EPOCH = date(2026, 11, 1)
TOP_STAGE = 4

# (stage, min account age in days, min confirmed check-ins)
LADDER = ((1, 7, 3), (2, 14, 7), (3, 21, 12), (4, 35, 20))


def stage_for(created_on: date | None, today: date, confirmed_checkins: int) -> int:
    if created_on is not None and created_on < UNLOCK_EPOCH:
        return TOP_STAGE
    age = max(0, (today - created_on).days) if created_on is not None else 0
    stage = 0
    for s, min_age, min_checkins in LADDER:
        if age >= min_age and confirmed_checkins >= min_checkins:
            stage = s
    return stage
