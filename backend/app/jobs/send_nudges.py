"""
Nudge dispatch job. Run every 5 minutes as a Cron Job:  python -m app.jobs.send_nudges

What it does: for each user who has a registered device AND an open task that could be triggering soon, it asks
NotificationsService.dispatch() what (if anything) to push right now. The policy (backoff, quiet hours, digest,
pause, daily cap) lives in services/nudge_policy.py; this file only walks users.

RLS: listing "who has devices + open tasks" must see ALL users, so that one query runs on a plain session (owner
connection, no `set local role`). Every per-user step then runs in its own transaction with that user's RLS
context applied -- same pattern as generate_retros. This module must never be imported by, or exposed through,
the HTTP app.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, or_, select

from app.config import Settings, get_settings
from app.dates import Clock, utc_now
from app.db import AsyncSessionLocal, apply_rls_context
from app.models import PushSubscriptionORM, TaskORM
from app.repositories.notification_repository import SqlAlchemyNotificationRepository
from app.repositories.pause_repository import SqlAlchemyPauseRepository
from app.repositories.profile_repository import SqlAlchemyProfileRepository
from app.repositories.task_repository import SqlAlchemyTaskRepository
from app.services.notifications_service import NotificationsService
from app.services.profile_service import ProfileService
from app.services.push import PushSender, WebPushSender

logger = logging.getLogger("lockin.jobs.nudges")

MAX_USERS_PER_RUN = 5000
PER_USER_TIMEOUT_SECONDS = 60
# A bare-date task triggers at the person's nudge hour in THEIR timezone, which can be well over a day away from
# UTC midnight; this margin keeps those users in the candidate list without scanning everyone.
TRIGGER_LOOKAHEAD = timedelta(days=2)


async def candidate_user_ids(clock: Clock = utc_now, limit: int = MAX_USERS_PER_RUN) -> list[UUID]:
    horizon = clock() + TRIGGER_LOOKAHEAD
    trigger = func.coalesce(TaskORM.remind_at, TaskORM.due_at)
    has_open_trigger = select(TaskORM.user_id).where(
        TaskORM.status == "open", or_(TaskORM.due_at.is_not(None), TaskORM.remind_at.is_not(None)),
        trigger <= horizon,
    )
    stmt = select(PushSubscriptionORM.user_id).where(PushSubscriptionORM.user_id.in_(has_open_trigger)).distinct()
    async with AsyncSessionLocal() as session:  # deliberately NO rls context: see module docstring
        rows = (await session.execute(stmt.limit(limit))).all()
    return sorted(r[0] for r in rows)


async def _run_user(user_id: UUID, sender: PushSender, settings: Settings, clock: Clock) -> int:
    async with AsyncSessionLocal() as session:
        async with session.begin():  # one transaction per user: a failure rolls back only that user
            if settings.rls_enforced:
                await apply_rls_context(session, user_id)
            service = NotificationsService(
                SqlAlchemyNotificationRepository(session),
                SqlAlchemyTaskRepository(session),
                SqlAlchemyPauseRepository(session),
                ProfileService(SqlAlchemyProfileRepository(session), clock),
                sender,
                settings.push_allowed_host_suffixes,
                clock,
            )
            return (await service.dispatch(user_id)).sent


async def run_once(sender: PushSender | None = None, clock: Clock = utc_now) -> dict[str, int]:
    settings = get_settings()
    sender = sender or WebPushSender(settings.vapid_private_key, settings.vapid_subject)
    counts = {"users": 0, "sent": 0, "errors": 0}
    if not sender.configured:
        logger.error("VAPID_PRIVATE_KEY / VAPID_SUBJECT are not set: nothing can be pushed.")
        counts["errors"] = 1
        return counts
    for user_id in await candidate_user_ids(clock):
        counts["users"] += 1
        try:
            counts["sent"] += await asyncio.wait_for(_run_user(user_id, sender, settings, clock), PER_USER_TIMEOUT_SECONDS)
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
