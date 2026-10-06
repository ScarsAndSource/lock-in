"""
Retro generation job. Run DAILY as a Cron Job:  python -m app.jobs.generate_retros

Daily, not weekly: generation is idempotent (one retro per user per week), and users
in different timezones finish their Sunday at different times. Each user's run uses
that user's RLS context in its own transaction.
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.config import Settings, get_settings
from app.dates import Clock, utc_now
from app.db import AsyncSessionLocal, apply_rls_context
from app.repositories.habit_repository import SqlAlchemyHabitRepository
from app.repositories.mission_repository import SqlAlchemyMissionRepository
from app.repositories.profile_repository import SqlAlchemyProfileRepository
from app.repositories.retro_repository import SqlAlchemyRetroRepository
from app.repositories.screen_time_repository import SqlAlchemyScreenTimeRepository
from app.repositories.sleep_repository import SqlAlchemySleepRepository
from app.security import FieldEncryptor
from app.services.insights_service import InsightsService
from app.services.llm import GroqClient, LLMClient
from app.services.missions_service import MissionsService
from app.services.profile_service import ProfileService
from app.services.retro_service import RetroService
from app.services.stats_service import StatsService
from app.services.study_service import StudyService
from app.services.urges_service import UrgesService

logger = logging.getLogger("lockin.jobs.retros")


async def active_user_ids() -> list[UUID]:
    """Returns distinct user_ids that have logged anything recently.
    Stub: returns empty list until a real query is wired in the users slice."""
    return []


def build_retro_service(session, llm: LLMClient, settings: Settings, clock: Clock = utc_now) -> RetroService:
    profiles = ProfileService(SqlAlchemyProfileRepository(session), clock)
    stats = StatsService(
        SqlAlchemyHabitRepository(session), SqlAlchemySleepRepository(session),
        SqlAlchemyScreenTimeRepository(session), profiles,
    )
    study = StudyService()
    urges = UrgesService()
    missions = MissionsService(SqlAlchemyMissionRepository(session), stats, profiles, clock)
    insights = InsightsService()
    return RetroService(
        SqlAlchemyRetroRepository(session), stats, study, urges, missions, insights, profiles, llm, clock,
    )


async def run_once(llm: LLMClient | None = None) -> dict[str, int]:
    settings = get_settings()
    llm = llm or GroqClient()
    counts = {"users": 0, "retros": 0, "errors": 0}
    for user_id in await active_user_ids():
        counts["users"] += 1
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    if settings.rls_enforced:
                        await apply_rls_context(session, user_id)
                    _, created = await build_retro_service(session, llm, settings).generate(user_id, None)
                    counts["retros"] += int(created)
        except Exception:  # noqa: BLE001
            counts["errors"] += 1
            logger.exception("retro generation failed for user %s", user_id)
    logger.info("retro job finished: %s", counts)
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_once())


if __name__ == "__main__":
    main()
