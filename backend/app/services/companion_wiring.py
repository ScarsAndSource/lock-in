"""
Builds the companion stack for ONE user-scoped DB session, outside FastAPI's dependency system.
Used by the nudge job (a cron process, no HTTP request) and by the unauthenticated push-action endpoint (the user
comes from a verified token, not a JWT). Same repositories and services as the HTTP app, so RLS and validation match.
"""
from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.dates import Clock
from app.repositories.checkin_repository import SqlAlchemyCheckinRepository
from app.repositories.companion_repository import SqlAlchemyCompanionRepository
from app.repositories.goal_repository import SqlAlchemyGoalRepository, SqlAlchemyIntentionRepository
from app.repositories.habit_repository import SqlAlchemyHabitRepository
from app.repositories.mood_repository import SqlAlchemyMoodRepository
from app.repositories.notification_repository import SqlAlchemyNotificationRepository
from app.repositories.pause_repository import SqlAlchemyPauseRepository
from app.repositories.profile_repository import SqlAlchemyProfileRepository
from app.repositories.screen_time_repository import SqlAlchemyScreenTimeRepository
from app.repositories.sleep_repository import SqlAlchemySleepRepository
from app.repositories.study_repository import SqlAlchemyStudySessionRepository, SqlAlchemySubjectRepository
from app.repositories.task_repository import SqlAlchemyTaskRepository
from app.repositories.urge_repository import SqlAlchemyUrgeRepository
from app.security import FieldEncryptor
from app.services import push_actions
from app.services.actions_service import ActionsService
from app.services.checkins_service import CheckinsService
from app.services.daily_pulse import DailyPulse
from app.services.companion_service import CompanionPlanner
from app.repositories.ingest_repository import SqlAlchemyIngestTokenRepository
from app.services.habits_service import HabitsService
from app.services.ingest_service import IngestService
from app.services.screen_time_service import ScreenTimeService
from app.services.sleep_service import SleepService
from app.repositories.insight_repository import SqlAlchemyInsightRepository
from app.services.insights_service import InsightsService
from app.services.intentions_service import IntentionsService
from app.services.llm import LLMClient, LLMUnavailableError, scoped
from app.services.notifications_service import NotificationsService
from app.services.profile_service import ProfileService
from app.services.push import PushSender
from app.services.stats_service import StatsService
from app.services.study_service import StudyService
from app.services.tasks_service import TasksService


class _NoLLM:
    """The job and the action endpoint never call a model; if something ever tries, it fails closed."""
    model = "none"

    async def complete(self, messages, *, max_tokens: int = 512, temperature: float = 0.3) -> str:
        raise LLMUnavailableError("No model in this context.")


def build_stack(
    session: AsyncSession, settings: Settings, clock: Clock, sender: PushSender | None = None,
    llm: LLMClient | None = None,
) -> SimpleNamespace:
    habit_repo, checkin_repo = SqlAlchemyHabitRepository(session), SqlAlchemyCheckinRepository(session)
    sleep_repo, screen_repo = SqlAlchemySleepRepository(session), SqlAlchemyScreenTimeRepository(session)
    pause_repo, urge_repo = SqlAlchemyPauseRepository(session), SqlAlchemyUrgeRepository(session)
    goal_repo, subject_repo = SqlAlchemyGoalRepository(session), SqlAlchemySubjectRepository(session)
    session_repo = SqlAlchemyStudySessionRepository(session)
    notif_repo, task_repo = SqlAlchemyNotificationRepository(session), SqlAlchemyTaskRepository(session)
    ledger = SqlAlchemyCompanionRepository(session)
    profiles = ProfileService(SqlAlchemyProfileRepository(session), clock)
    secret = push_actions.derive_secret(settings.push_action_secret, settings.field_encryption_key)

    mood_repo = SqlAlchemyMoodRepository(session)
    stats = StatsService(
        habit_repo, sleep_repo, screen_repo, profiles, session_repo, urge_repo, pause_repo, mood_repo, task_repo,
    )
    study = StudyService(subject_repo, session_repo, clock)
    intentions = IntentionsService(
        SqlAlchemyIntentionRepository(session), habit_repo, subject_repo, stats, profiles, clock, pauses=pause_repo,
    )
    tasks = TasksService(task_repo, notif_repo, profiles, _NoLLM(), clock)
    checkins = CheckinsService(
        habit_repo, checkin_repo, FieldEncryptor(settings.field_encryption_key, settings.old_encryption_keys),
        sleep_repo, screen_repo, clock, goals=goal_repo, pauses=pause_repo, mood_repo=mood_repo,
    )
    insight_repo = SqlAlchemyInsightRepository(session)
    # With no model the pulse still works: insights are stored with the deterministic statement (narrated=False).
    insights = InsightsService(insight_repo, stats, clock, llm=scoped(llm, "insight") if llm is not None else None)
    planner = CompanionPlanner(
        ledger, habit_repo, checkin_repo, urge_repo, sleep_repo, goal_repo, study, intentions, stats, pause_repo,
        tasks=task_repo, insights=insight_repo,
    )
    ns = SimpleNamespace(planner=planner, ledger=ledger, profiles=profiles, insights=insights)
    ns.pulse = DailyPulse(ledger, checkin_repo, insights)
    ns.ingest = IngestService(
        SqlAlchemyIngestTokenRepository(session), SleepService(sleep_repo, clock), sleep_repo,
        ScreenTimeService(screen_repo, clock), profiles, secret, clock,
    )
    ns.actions = ActionsService(
        ledger=ledger, tasks=tasks, checkins=checkins, habits=HabitsService(habit_repo, clock), profiles=profiles,
        secret=secret, clock=clock,
    )
    if sender is not None:
        ns.notifications = NotificationsService(
            notif_repo, task_repo, pause_repo, profiles, sender, settings.push_allowed_host_suffixes, clock,
            ledger=ledger, companion=planner, action_secret=secret, api_url=settings.public_api_url,
        )
    return ns
