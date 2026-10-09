"""
Retro generation job. Run DAILY as a Cron Job:  python -m app.jobs.generate_retros

Daily, not weekly: generation is idempotent (one retro per user per week; an existing retro
returns before any gathering or LLM work), and users in different timezones finish their
Sunday at different times.

RLS: listing "who is active" needs to see ALL users, so that one query runs on a plain
session (owner connection, no `set local role`). Every per-user step then runs in its own
transaction with that user's RLS context applied. This module must never be imported by,
or exposed through, the HTTP app.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, union

from app.config import Settings, get_settings
from app.dates import Clock, utc_now
from app.db import AsyncSessionLocal, apply_rls_context
from app.models import DailyCheckinORM, HabitLogORM, ScreenTimeLogORM, SleepLogORM
from app.repositories.habit_repository import SqlAlchemyHabitRepository
from app.repositories.insight_repository import SqlAlchemyInsightRepository
from app.repositories.mission_repository import SqlAlchemyMissionRepository
from app.repositories.profile_repository import SqlAlchemyProfileRepository
from app.repositories.retro_repository import SqlAlchemyRetroRepository
from app.repositories.screen_time_repository import SqlAlchemyScreenTimeRepository
from app.repositories.sleep_repository import SqlAlchemySleepRepository
from app.services.insights_service import InsightsService
from app.services.llm import GroqClient, LLMClient
from app.services.missions_service import MissionsService
from app.services.profile_service import ProfileService
from app.services.retro_service import RetroService
from app.services.stats_service import StatsService
from app.services.study_service import StudyService
from app.services.urges_service import UrgesService

logger = logging.getLogger("lockin.jobs.retros")

ACTIVE_WINDOW_DAYS = 14        # covers the whole week being retro'd, plus slack
MAX_USERS_PER_RUN = 5000
PER_USER_TIMEOUT_SECONDS = 120


async def active_user_ids(
    clock: Clock = utc_now, window_days: int = ACTIVE_WINDOW_DAYS, limit: int = MAX_USERS_PER_RUN,
) -> list[UUID]:
    """Users with a check-in or any habit/sleep/screen log in the last `window_days` days."""
    since = (clock() - timedelta(days=window_days)).date()
    stmt = union(
        select(DailyCheckinORM.user_id).where(DailyCheckinORM.checkin_date >= since),
        select(HabitLogORM.user_id).where(HabitLogORM.log_date >= since),
        select(SleepLogORM.user_id).where(SleepLogORM.log_date >= since),
        select(ScreenTimeLogORM.user_id).where(ScreenTimeLogORM.log_date >= since),
    )
    async with AsyncSessionLocal() as session:  # deliberately NO rls context: see module docstring
        rows = (await session.execute(stmt)).all()
    return sorted({r[0] for r in rows})[:limit]


def build_retro_service(session, llm: LLMClient, settings: Settings, clock: Clock = utc_now) -> RetroService:
    profiles = ProfileService(SqlAlchemyProfileRepository(session), clock)
    stats = StatsService(
        SqlAlchemyHabitRepository(session), SqlAlchemySleepRepository(session),
        SqlAlchemyScreenTimeRepository(session), profiles,
    )
    study = StudyService()
    urges = UrgesService()
    missions = MissionsService(SqlAlchemyMissionRepository(session), stats, profiles, clock)
    insights = InsightsService(SqlAlchemyInsightRepository(session), stats, clock)
    return RetroService(
        SqlAlchemyRetroRepository(session), stats, study, urges, missions, insights, profiles, llm, clock,
    )


async def _run_user(user_id: UUID, llm: LLMClient, settings: Settings, clock: Clock) -> bool:
    async with AsyncSessionLocal() as session:
        async with session.begin():  # one transaction per user: a failure rolls back only that user
            if settings.rls_enforced:
                await apply_rls_context(session, user_id)
            _, created = await build_retro_service(session, llm, settings, clock).generate(user_id, None)
            return created


async def run_once(llm: LLMClient | None = None, clock: Clock = utc_now) -> dict[str, int]:
    settings = get_settings()
    llm = llm or GroqClient()
    counts = {"users": 0, "retros": 0, "errors": 0}
    for user_id in await active_user_ids(clock):
        counts["users"] += 1
        try:
            created = await asyncio.wait_for(_run_user(user_id, llm, settings, clock), PER_USER_TIMEOUT_SECONDS)
            counts["retros"] += int(created)
        except Exception:  # noqa: BLE001 -- includes timeouts; one user never blocks the rest
            counts["errors"] += 1
            logger.exception("retro generation failed for user %s", user_id)
    logger.info("retro job finished: %s", counts)
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    counts = asyncio.run(run_once())
    if counts["users"] and counts["errors"] == counts["users"]:
        sys.exit(1)  # everything failed -> make the Render cron run show red


if __name__ == "__main__":
    main()
