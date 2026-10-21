"""
Same-day insights: the app reacts the day the data arrives, not when the weekly retro happens to run.

Before this, insights refreshed only when the weekly retro completed or someone tapped refresh, so a pattern that was
already visible in the data waited days to be said out loud. The pulse runs inside the companion tick:

  once per local day, and only after the person CONFIRMED that day's check-in (the day's data is in),
  run InsightsService.refresh() -- the same deterministic pattern finder, the same validators, the same
  7-day de-duplication and the same "rate your old insights first" gate, so it can never nag or repeat itself.

The once-a-day marker is a row in the push ledger (kind "pulse"), reserved in the SAME transaction as the refresh: a
crash rolls both back and the next tick retries; two overlapping runs cannot both pass the unique key. The marker is not
a push and does not count toward the daily push budget. The companion planner then offers ONE neutral push
("a pattern showed up") if a new insight exists today. Its lock-screen text never names the pattern, because patterns
can involve sensitive domains.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.domain import CompanionPush
from app.repositories.checkin_repository import CheckinRepository
from app.repositories.companion_repository import CompanionRepository
from app.services.insights_service import InsightsService

logger = logging.getLogger("lockin.pulse")


@dataclass(slots=True)
class PulseResult:
    created: int = 0
    skipped: str | None = None     # not_confirmed | already_ran | rate_previous_first | no_patterns | no_new_patterns


class DailyPulse:
    def __init__(self, ledger: CompanionRepository, checkins: CheckinRepository, insights: InsightsService):
        self._ledger, self._checkins, self._insights = ledger, checkins, insights

    async def run(self, user_id: UUID, now: datetime, tz: ZoneInfo) -> PulseResult:
        today = now.astimezone(tz).date()
        row = await self._checkins.get(user_id, today)
        if row is None or row.confirmed_at is None:
            return PulseResult(skipped="not_confirmed")            # data isn't in yet: don't burn the day's run
        reserved = await self._ledger.reserve(CompanionPush(
            id=uuid4(), user_id=user_id, kind="pulse", key=f"pulse:{today.isoformat()}", local_date=today, sent_at=now,
        ))
        if not reserved:
            return PulseResult(skipped="already_ran")
        result = await self._insights.refresh(user_id)
        logger.info("pulse user=%s created=%d skipped=%s", user_id, len(result.created), result.skipped_reason)
        return PulseResult(created=len(result.created), skipped=result.skipped_reason)
