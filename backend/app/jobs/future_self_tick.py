"""
Notes-to-future-self job. Run every 5 minutes as a Cron Job, OFFSET from send_nudges (*/5) and companion_tick (2-59/5):

    python -m app.jobs.future_self_tick        (schedule "4-59/5 * * * *")

All three jobs read and update the person's daily push counter; distinct minutes keep them from losing an increment.
Same rules as companion_tick: one transaction per user with that user's RLS context; never imported by the HTTP app.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from uuid import UUID

from sqlalchemy import select

from app.config import Settings, get_settings
from app.dates import Clock, utc_now
from app.db import AsyncSessionLocal, apply_rls_context
from app.models_growth import FutureMessageORM
from app.repositories.growth_repository import SqlAlchemyGrowthRepository
from app.repositories.notification_repository import SqlAlchemyNotificationRepository
from app.repositories.pause_repository import SqlAlchemyPauseRepository
from app.repositories.profile_repository import SqlAlchemyProfileRepository
from app.repositories.task_repository import SqlAlchemyTaskRepository
from app.repositories.urge_repository import SqlAlchemyUrgeRepository
from app.services.future_self_dispatch import FutureSelfDispatcher
from app.services.notifications_service import NotificationsService
from app.services.profile_service import ProfileService
from app.services.push import PushSender, WebPushSender

logger = logging.getLogger("lockin.jobs.future_self")

MAX_USERS_PER_RUN = 5000
PER_USER_TIMEOUT_SECONDS = 60


async def candidate_user_ids(limit: int = MAX_USERS_PER_RUN) -> list[UUID]:
    async with AsyncSessionLocal() as session:  # deliberately NO rls context: it must see every user
        stmt = select(FutureMessageORM.user_id).where(FutureMessageORM.active.is_(True)).distinct().limit(limit)
        rows = (await session.execute(stmt)).all()
    return sorted(r[0] for r in rows)


def build_dispatcher(session, sender: PushSender, settings: Settings, clock: Clock) -> FutureSelfDispatcher:
    profiles = ProfileService(SqlAlchemyProfileRepository(session), clock)
    notif_repo = SqlAlchemyNotificationRepository(session)
    pauses = SqlAlchemyPauseRepository(session)
    notifications = NotificationsService(
        notif_repo, SqlAlchemyTaskRepository(session), pauses, profiles, sender,
        settings.push_allowed_host_suffixes, clock,
    )
    return FutureSelfDispatcher(
        SqlAlchemyGrowthRepository(session), SqlAlchemyUrgeRepository(session), notifications, notif_repo,
        pauses, profiles, sender, clock,
    )


async def _run_user(user_id: UUID, sender: PushSender, settings: Settings, clock: Clock) -> bool:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            if settings.rls_enforced:
                await apply_rls_context(session, user_id)
            return (await build_dispatcher(session, sender, settings, clock).tick(user_id)).sent


async def run_once(sender: PushSender | None = None, clock: Clock = utc_now) -> dict[str, int]:
    settings = get_settings()
    sender = sender or WebPushSender(settings.vapid_private_key, settings.vapid_subject)
    counts = {"users": 0, "sent": 0, "errors": 0}
    if not sender.configured:
        logger.error("VAPID_PRIVATE_KEY / VAPID_SUBJECT are not set: nothing can be pushed.")
        counts["errors"] = 1
        return counts
    for user_id in await candidate_user_ids():
        counts["users"] += 1
        try:
            counts["sent"] += int(await asyncio.wait_for(
                _run_user(user_id, sender, settings, clock), PER_USER_TIMEOUT_SECONDS,
            ))
        except Exception:  # noqa: BLE001 -- includes timeouts; one user never blocks the rest
            counts["errors"] += 1
            logger.exception("future-self tick failed for user %s", user_id)
    logger.info("future-self job finished: %s", counts)
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    counts = asyncio.run(run_once())
    if counts["errors"] and counts["errors"] >= max(1, counts["users"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
