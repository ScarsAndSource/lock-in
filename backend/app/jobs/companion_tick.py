"""
Companion moments job. Run every 5 minutes as a Cron Job, OFFSET from send_nudges:

    python -m app.jobs.companion_tick          (e.g. schedule "2-59/5 * * * *"; send_nudges uses "*/5 * * * *")

For each user with a registered device it asks MomentsService.tick() whether the companion has something to say right
now (morning / evening). All the rules (learned times, shared push budget, quiet hours, pause, once per day) live in
services/moments_service.py; this file only walks users. Once a night it also trims old usage events.

RLS: the "who has devices" listing and the nightly trim see ALL users, so those run on a plain owner session. Every
per-user step runs in its own transaction with that user's RLS context, same pattern as send_nudges. This module must
never be imported by, or exposed through, the HTTP app.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select

from app.config import Settings, get_settings
from app.dates import Clock, utc_now
from app.db import AsyncSessionLocal, apply_rls_context
from app.models import PushSubscriptionORM
from app.repositories.checkin_repository import SqlAlchemyCheckinRepository
from app.repositories.companion_repository import SqlAlchemyCompanionRepository, prune_events
from app.repositories.send_time_repository import SqlAlchemySendTimeRepository, prune_outcomes
from app.services.send_time import SendTimeService
from app.repositories.goal_repository import SqlAlchemyGoalRepository, SqlAlchemyIntentionRepository
from app.repositories.habit_repository import SqlAlchemyHabitRepository
from app.repositories.mood_repository import SqlAlchemyMoodRepository
from app.repositories.notification_repository import SqlAlchemyNotificationRepository
from app.repositories.pause_repository import SqlAlchemyPauseRepository
from app.repositories.profile_repository import SqlAlchemyProfileRepository
from app.repositories.screen_time_repository import SqlAlchemyScreenTimeRepository
from app.repositories.sleep_repository import SqlAlchemySleepRepository
from app.repositories.task_repository import SqlAlchemyTaskRepository
from app.security import get_field_encryptor
from app.services.checkins_service import CheckinsService
from app.services.companion_service import CompanionService
from app.services.moments_service import MomentsService
from app.services.notifications_service import NotificationsService
from app.services.profile_service import ProfileService
from app.services.push import PushSender, WebPushSender
from app.services.tasks_service import TasksService

logger = logging.getLogger("lockin.jobs.companion")

MAX_USERS_PER_RUN = 5000
PER_USER_TIMEOUT_SECONDS = 60
EVENT_RETENTION = timedelta(days=120)
PRUNE_UTC_HOUR = 21   # ~02:30 IST: one quiet trim per day, run in the first five minutes of that hour


async def candidate_user_ids(limit: int = MAX_USERS_PER_RUN) -> list[UUID]:
    async with AsyncSessionLocal() as session:  # deliberately NO rls context: see module docstring
        rows = (await session.execute(select(PushSubscriptionORM.user_id).distinct().limit(limit))).all()
    return sorted(r[0] for r in rows)


def build_service(session, sender: PushSender, settings: Settings, clock: Clock) -> MomentsService:
    profiles = ProfileService(SqlAlchemyProfileRepository(session), clock)
    notif_repo = SqlAlchemyNotificationRepository(session)
    task_repo = SqlAlchemyTaskRepository(session)
    pauses = SqlAlchemyPauseRepository(session)
    checkins = CheckinsService(
        SqlAlchemyHabitRepository(session), SqlAlchemyCheckinRepository(session), get_field_encryptor(settings),
        SqlAlchemySleepRepository(session), SqlAlchemyScreenTimeRepository(session), clock,
        goals=SqlAlchemyGoalRepository(session), pauses=pauses, mood_repo=SqlAlchemyMoodRepository(session),
    )
    # The companion only reads the task focus, which never touches the model, so no LLM client is needed here.
    tasks = TasksService(task_repo, notif_repo, profiles, None, clock)  # type: ignore[arg-type]
    companion = CompanionService(
        SqlAlchemyCompanionRepository(session), checkins, tasks, profiles, SqlAlchemyIntentionRepository(session), clock,
    )
    notifications = NotificationsService(
        notif_repo, task_repo, pauses, profiles, sender, settings.push_allowed_host_suffixes, clock,
    )
    send_time = SendTimeService(
        SqlAlchemySendTimeRepository(session), SqlAlchemyCompanionRepository(session), notif_repo, profiles, clock,
    )
    return MomentsService(
        SqlAlchemyCompanionRepository(session), companion, notifications, notif_repo, pauses, profiles, sender, clock,
        send_time,
    )


async def _run_user(user_id: UUID, sender: PushSender, settings: Settings, clock: Clock) -> bool:
    async with AsyncSessionLocal() as session:
        async with session.begin():  # one transaction per user: a failure rolls back only that user
            if settings.rls_enforced:
                await apply_rls_context(session, user_id)
            return (await build_service(session, sender, settings, clock).tick(user_id)).sent


async def run_once(sender: PushSender | None = None, clock: Clock = utc_now) -> dict[str, int]:
    settings = get_settings()
    sender = sender or WebPushSender(settings.vapid_private_key, settings.vapid_subject)
    counts = {"users": 0, "sent": 0, "errors": 0, "pruned": 0}
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
            logger.exception("companion tick failed for user %s", user_id)
    now = clock()
    if now.hour == PRUNE_UTC_HOUR and now.minute < 5:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                counts["pruned"] = await prune_events(session, now - EVENT_RETENTION)
                counts["pruned"] += await prune_outcomes(session, (now - EVENT_RETENTION).date())
    logger.info("companion job finished: %s", counts)
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    counts = asyncio.run(run_once())
    if counts["errors"] and counts["errors"] >= max(1, counts["users"]):
        sys.exit(1)  # misconfigured, or everything failed -> make the Render cron run show red


if __name__ == "__main__":
    main()
