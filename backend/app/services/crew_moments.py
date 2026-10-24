"""Feeds the companion planner the three crew moments (Sunday card, boost request, buddy-deal prompt).
One cheap read per planner run; the buddy check only costs more for the rare user who has an active deal.
Everything here runs in the user's own RLS context. A crew failure must never cost anyone their other reminders,
so the whole block runs inside a savepoint and is swallowed on error."""
from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import UUID

from app.services import companion_policy as cp
from app.services.schedule import week_start

logger = logging.getLogger("lockin.crew_moments")
SUNDAY_HOUR = 19            # Crew Sunday opens in the evening
CIVIL_FROM, CIVIL_TO = 9, 21  # an auto-sent buddy message never goes out at night


class CrewMoments:
    def __init__(self, repo, crew):
        self._repo, self._crew = repo, crew

    async def load(self, ctx: cp.CompanionContext, user_id: UUID, local: datetime, sent: set[str]) -> None:
        try:
            async with self._repo.savepoint():
                await self._load(ctx, user_id, local, sent)
        except Exception:  # noqa: BLE001 -- logged; the rest of the planner carries on
            logger.exception("crew moments failed for user %s", user_id)

    async def _load(self, ctx: cp.CompanionContext, user_id: UUID, local: datetime, sent: set[str]) -> None:
        today = local.date()
        week = week_start(today)
        res = await self._repo.moments(week)
        if res.get("error"):
            return

        for b in res.get("boosts", []):
            if f"crew_boost:{b['id']}" not in sent:
                ctx.crew_boost = cp.CrewBoost(UUID(b["id"]), UUID(b["crew_id"]), b["from_username"])
                break

        if (today.weekday() == 6 and local.hour >= SUNDAY_HOUR and res.get("in_crew") and not res.get("closed")
                and f"crew_sunday:{week.isoformat()}" not in sent):
            ctx.crew_sunday_week = week.isoformat()

        if local.hour < CIVIL_FROM:
            return
        for d in res.get("deals", []):
            since = date.fromisoformat(d["armed_from"]) if d.get("armed_from") else today
            if await self._crew.miss_streak(user_id, today, since) < d["threshold"]:
                continue
            if d["auto_send"]:                       # their own pre-agreed switch, and only at a civil hour
                if local.hour < CIVIL_TO:
                    await self._repo.buddy_send(UUID(d["id"]), today)
                continue
            if ctx.crew_buddy is None and f"crew_buddy:{d['id']}:{since.isoformat()}" not in sent:
                ctx.crew_buddy = cp.CrewBuddy(UUID(d["id"]), d["buddy_username"], since.isoformat())
