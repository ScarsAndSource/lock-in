"""
Nudge + companion dispatch job. Run every 5 minutes as a Cron Job:  python -m app.jobs.send_nudges

What it does: for each user who has a registered device (and has not switched pushes off), it asks
NotificationsService.dispatch() what (if anything) to push right now. That covers task reminders AND the companion
moments (check-in, habits, risk windows, wind-down, study) under ONE daily budget. The policies (backoff, quiet hours,
digest, pause, daily cap) live in services/nudge_policy.py and services/companion_policy.py; this file only walks users.
Before the companion layer only users with an open task were candidates; now everyone with a device is, because
"never opens the app" must not mean "never hears about anything that matters". Data is loaded lazily per user, so
a quiet user costs a couple of cheap queries.

RLS: listing "who has devices + open tasks" must see ALL users, so that one query runs on a plain session (owner
connection, no `set local role`). Every per-user step then runs in its own transaction with that user's RLS
context applied -- same pattern as generate_retros. This module must never be imported by, or exposed through,
the HTTP app.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from uuid import UUID

from sqlalchemy import or_, select

from app.config import Settings, get_settings
from app.dates import Clock, utc_now
from app.db import AsyncSessionLocal, apply_rls_context
from app.models import NotificationPrefsORM, PushSubscriptionORM
from app.repositories.llm_usage_repository import SqlAlchemyLlmUsageRepository
from app.services.companion_wiring import build_stack
from app.services.llm import BudgetedLLM, GroqClient, LLMClient, LLMError
from app.services.task_time import zone
from app.services.push import PushSender, WebPushSender

logger = logging.getLogger("lockin.jobs.nudges")

MAX_USERS_PER_RUN = 5000
PER_USER_TIMEOUT_SECONDS = 60


async def candidate_user_ids(clock: Clock = utc_now, limit: int = MAX_USERS_PER_RUN) -> list[UUID]:
    """Everyone with a registered device who hasn't switched pushes off (no prefs row = defaults = on)."""
    stmt = (
        select(PushSubscriptionORM.user_id)
        .outerjoin(NotificationPrefsORM, NotificationPrefsORM.user_id == PushSubscriptionORM.user_id)
        .where(or_(NotificationPrefsORM.push_enabled.is_(None), NotificationPrefsORM.push_enabled.is_(True)))
        .distinct()
    )
    async with AsyncSessionLocal() as session:  # deliberately NO rls context: see module docstring
        rows = (await session.execute(stmt.limit(limit))).all()
    return sorted(r[0] for r in rows)


async def _run_user(
    user_id: UUID, sender: PushSender, settings: Settings, clock: Clock, inner_llm: LLMClient | None = None,
) -> int:
    async with AsyncSessionLocal() as session:
        async with session.begin():  # one transaction per user: a failure rolls back only that user
            if settings.rls_enforced:
                await apply_rls_context(session, user_id)
            llm = BudgetedLLM(
                inner_llm, SqlAlchemyLlmUsageRepository(AsyncSessionLocal, rls_enforced=settings.rls_enforced),
                user_id, settings.llm_daily_call_cap, "insight", clock,
            ) if inner_llm is not None else None
            stack = build_stack(session, settings, clock, sender, llm)
            tz = zone((await stack.profiles.get(user_id)).timezone)
            try:   # same-day insights: a failure here must never cost the person their reminders
                await stack.pulse.run(user_id, clock(), tz)
            except LLMError:
                logger.warning("pulse skipped for user %s: model unavailable", user_id)
            return (await stack.notifications.dispatch(user_id)).sent


async def run_once(
    sender: PushSender | None = None, clock: Clock = utc_now, llm: LLMClient | None = None,
) -> dict[str, int]:
    settings = get_settings()
    if llm is None and settings.groq_api_key:
        llm = GroqClient(
            settings.groq_api_key, settings.groq_model, settings.groq_timeout_seconds, settings.groq_base_url,
            max_retries=settings.groq_max_retries,
        )
    sender = sender or WebPushSender(settings.vapid_private_key, settings.vapid_subject)
    counts = {"users": 0, "sent": 0, "errors": 0}
    if not sender.configured:
        logger.error("VAPID_PRIVATE_KEY / VAPID_SUBJECT are not set: nothing can be pushed.")
        counts["errors"] = 1
        return counts
    for user_id in await candidate_user_ids(clock):
        counts["users"] += 1
        try:
            counts["sent"] += await asyncio.wait_for(_run_user(user_id, sender, settings, clock, llm), PER_USER_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001 -- includes timeouts; one user never blocks the rest
            counts["errors"] += 1
            logger.exception("nudge dispatch failed for user %s", user_id)
    logger.info("nudge job finished: %s", counts)
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    counts = asyncio.run(run_once())
    if counts["errors"] and counts["errors"] >= max(1, counts["users"]):
        sys.exit(1)  # misconfigured, or everything failed -> make the Render cron run show red


if __name__ == "__main__":
    main()
