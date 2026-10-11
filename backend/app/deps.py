from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.dates import Clock, utc_now
from app.db import get_db
from app.repositories.account_repository import SqlAlchemyAccountRepository
from app.repositories.chat_thread_repository import SqlAlchemyChatThreadRepository
from app.repositories.checkin_repository import SqlAlchemyCheckinRepository
from app.repositories.goal_repository import SqlAlchemyGoalRepository, SqlAlchemyIntentionRepository
from app.repositories.habit_repository import SqlAlchemyHabitRepository
from app.repositories.insight_repository import SqlAlchemyInsightRepository
from app.repositories.llm_usage_repository import SqlAlchemyLlmUsageRepository
from app.repositories.mission_repository import SqlAlchemyMissionRepository
from app.repositories.pause_repository import SqlAlchemyPauseRepository
from app.repositories.profile_repository import SqlAlchemyProfileRepository
from app.repositories.retro_repository import SqlAlchemyRetroRepository
from app.repositories.screen_time_repository import SqlAlchemyScreenTimeRepository
from app.repositories.sleep_repository import SqlAlchemySleepRepository
from app.repositories.study_repository import SqlAlchemyStudySessionRepository, SqlAlchemySubjectRepository
from app.repositories.urge_repository import SqlAlchemyUrgeRepository
from app.security import FieldEncryptor, get_current_user_id, get_field_encryptor
from app.services.account_service import AccountService
from app.services.chat_service import ChatService
from app.services.chat_threads_service import ChatThreadsService
from app.services.checkins_service import CheckinsService
from app.services.goals_service import GoalsService
from app.services.habits_service import HabitsService
from app.services.insights_service import InsightsService
from app.services.intentions_service import IntentionsService
from app.services.llm import BudgetedLLM, GroqClient, LLMClient, scoped
from app.services.missions_service import MissionsService
from app.services.pauses_service import PausesService
from app.services.pause_shortcuts_service import PauseShortcutsService
from app.services.profile_service import ProfileService
from app.services.retro_service import RetroService
from app.services.screen_time_service import ScreenTimeService
from app.services.sleep_service import SleepService
from app.services.stats_service import StatsService
from app.services.study_service import StudyService
from app.services.urges_service import UrgesService


def get_clock() -> Clock:
    return utc_now


# ---- repositories
def get_habit_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyHabitRepository:
    return SqlAlchemyHabitRepository(session)


def get_checkin_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyCheckinRepository:
    return SqlAlchemyCheckinRepository(session)


def get_sleep_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemySleepRepository:
    return SqlAlchemySleepRepository(session)


def get_screen_time_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyScreenTimeRepository:
    return SqlAlchemyScreenTimeRepository(session)


def get_profile_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyProfileRepository:
    return SqlAlchemyProfileRepository(session)


def get_mission_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyMissionRepository:
    return SqlAlchemyMissionRepository(session)


def get_account_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyAccountRepository:
    return SqlAlchemyAccountRepository(session)


def get_retro_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyRetroRepository:
    return SqlAlchemyRetroRepository(session)


def get_insight_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyInsightRepository:
    return SqlAlchemyInsightRepository(session)


def get_llm_usage_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyLlmUsageRepository:
    return SqlAlchemyLlmUsageRepository(session)


def get_chat_thread_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyChatThreadRepository:
    return SqlAlchemyChatThreadRepository(session)


def get_pause_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyPauseRepository:
    return SqlAlchemyPauseRepository(session)



def get_subject_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemySubjectRepository:
    return SqlAlchemySubjectRepository(session)


def get_study_session_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyStudySessionRepository:
    return SqlAlchemyStudySessionRepository(session)


def get_urge_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyUrgeRepository:
    return SqlAlchemyUrgeRepository(session)


def get_goal_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyGoalRepository:
    return SqlAlchemyGoalRepository(session)


def get_intention_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyIntentionRepository:
    return SqlAlchemyIntentionRepository(session)


# ---- services
def get_habits_service(
    habit_repo: SqlAlchemyHabitRepository = Depends(get_habit_repository),
    clock: Clock = Depends(get_clock),
) -> HabitsService:
    return HabitsService(habit_repo, clock)


def get_checkins_service(
    habit_repo: SqlAlchemyHabitRepository = Depends(get_habit_repository),
    checkin_repo: SqlAlchemyCheckinRepository = Depends(get_checkin_repository),
    encryptor: FieldEncryptor = Depends(get_field_encryptor),
    sleep_repo: SqlAlchemySleepRepository = Depends(get_sleep_repository),
    screen_repo: SqlAlchemyScreenTimeRepository = Depends(get_screen_time_repository),
    clock: Clock = Depends(get_clock),
    goal_repo: SqlAlchemyGoalRepository = Depends(get_goal_repository),
    pause_repo: SqlAlchemyPauseRepository = Depends(get_pause_repository),
) -> CheckinsService:
    return CheckinsService(
        habit_repo, checkin_repo, encryptor, sleep_repo, screen_repo, clock, goals=goal_repo, pauses=pause_repo,
    )


def get_sleep_service(
    repo: SqlAlchemySleepRepository = Depends(get_sleep_repository),
    clock: Clock = Depends(get_clock),
) -> SleepService:
    return SleepService(repo, clock)


def get_screen_time_service(
    repo: SqlAlchemyScreenTimeRepository = Depends(get_screen_time_repository),
    clock: Clock = Depends(get_clock),
) -> ScreenTimeService:
    return ScreenTimeService(repo, clock)


def get_profile_service(
    repo: SqlAlchemyProfileRepository = Depends(get_profile_repository),
    clock: Clock = Depends(get_clock),
) -> ProfileService:
    return ProfileService(repo, clock)


def get_stats_service(
    habit_repo: SqlAlchemyHabitRepository = Depends(get_habit_repository),
    sleep_repo: SqlAlchemySleepRepository = Depends(get_sleep_repository),
    screen_repo: SqlAlchemyScreenTimeRepository = Depends(get_screen_time_repository),
    profiles: ProfileService = Depends(get_profile_service),
    study_repo: SqlAlchemyStudySessionRepository = Depends(get_study_session_repository),
    urge_repo: SqlAlchemyUrgeRepository = Depends(get_urge_repository),
    pause_repo: SqlAlchemyPauseRepository = Depends(get_pause_repository),
) -> StatsService:
    return StatsService(habit_repo, sleep_repo, screen_repo, profiles, study_repo, urge_repo, pause_repo)


def get_missions_service(
    repo: SqlAlchemyMissionRepository = Depends(get_mission_repository),
    stats: StatsService = Depends(get_stats_service),
    profiles: ProfileService = Depends(get_profile_service),
    clock: Clock = Depends(get_clock),
) -> MissionsService:
    return MissionsService(repo, stats, profiles, clock)


def get_account_service(
    repo: SqlAlchemyAccountRepository = Depends(get_account_repository),
    encryptor: FieldEncryptor = Depends(get_field_encryptor),
    clock: Clock = Depends(get_clock),
) -> AccountService:
    return AccountService(repo, encryptor, clock)


def get_llm_client(
    user_id: UUID = Depends(get_current_user_id),
    usage: SqlAlchemyLlmUsageRepository = Depends(get_llm_usage_repository),
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
) -> LLMClient:
    """Groq behind the per-user daily cap. With no GROQ_API_KEY every call raises LLMUnavailableError at call time and callers use their deterministic fallbacks."""
    inner = GroqClient(
        settings.groq_api_key,
        settings.groq_model,
        settings.groq_timeout_seconds,
        settings.groq_base_url,
    )
    return BudgetedLLM(inner, usage, user_id, settings.llm_daily_call_cap, "chat", clock)


def get_study_service(
    subjects: SqlAlchemySubjectRepository = Depends(get_subject_repository),
    sessions: SqlAlchemyStudySessionRepository = Depends(get_study_session_repository),
    clock: Clock = Depends(get_clock),
) -> StudyService:
    return StudyService(subjects, sessions, clock)


def get_urges_service(
    repo: SqlAlchemyUrgeRepository = Depends(get_urge_repository),
    encryptor: FieldEncryptor = Depends(get_field_encryptor),
    profiles: ProfileService = Depends(get_profile_service),
    clock: Clock = Depends(get_clock),
) -> UrgesService:
    return UrgesService(repo, encryptor, profiles, clock)


def get_goals_service(
    goals: SqlAlchemyGoalRepository = Depends(get_goal_repository),
    habits: SqlAlchemyHabitRepository = Depends(get_habit_repository),
    sleep: SqlAlchemySleepRepository = Depends(get_sleep_repository),
    screen: SqlAlchemyScreenTimeRepository = Depends(get_screen_time_repository),
    stats: StatsService = Depends(get_stats_service),
    study: StudyService = Depends(get_study_service),
    urges: UrgesService = Depends(get_urges_service),
    profiles: ProfileService = Depends(get_profile_service),
    clock: Clock = Depends(get_clock),
) -> GoalsService:
    return GoalsService(goals, habits, sleep, screen, stats, study, urges, profiles, clock)


def get_intentions_service(
    repo: SqlAlchemyIntentionRepository = Depends(get_intention_repository),
    habits: SqlAlchemyHabitRepository = Depends(get_habit_repository),
    subjects: SqlAlchemySubjectRepository = Depends(get_subject_repository),
    stats: StatsService = Depends(get_stats_service),
    profiles: ProfileService = Depends(get_profile_service),
    clock: Clock = Depends(get_clock),
    pauses: SqlAlchemyPauseRepository = Depends(get_pause_repository),
) -> IntentionsService:
    return IntentionsService(repo, habits, subjects, stats, profiles, clock, pauses=pauses)


def get_pauses_service(
    repo: SqlAlchemyPauseRepository = Depends(get_pause_repository),
    profiles: ProfileService = Depends(get_profile_service),
    clock: Clock = Depends(get_clock),
    habits: SqlAlchemyHabitRepository = Depends(get_habit_repository),
) -> PausesService:
    return PausesService(repo, profiles, clock, habits)


def get_insights_service(
    repo: SqlAlchemyInsightRepository = Depends(get_insight_repository),
    stats: StatsService = Depends(get_stats_service),
    clock: Clock = Depends(get_clock),
    llm: LLMClient = Depends(get_llm_client),
) -> InsightsService:
    return InsightsService(repo, stats, clock, llm=scoped(llm, "insight"))


def get_retro_service(
    repo: SqlAlchemyRetroRepository = Depends(get_retro_repository),
    stats: StatsService = Depends(get_stats_service),
    study: StudyService = Depends(get_study_service),
    urges: UrgesService = Depends(get_urges_service),
    missions: MissionsService = Depends(get_missions_service),
    insights: InsightsService = Depends(get_insights_service),
    profiles: ProfileService = Depends(get_profile_service),
    llm: LLMClient = Depends(get_llm_client),
    clock: Clock = Depends(get_clock),
) -> RetroService:
    return RetroService(repo, stats, study, urges, missions, insights, profiles, scoped(llm, "retro"), clock)


def get_chat_service(
    stats: StatsService = Depends(get_stats_service),
    study: StudyService = Depends(get_study_service),
    urges: UrgesService = Depends(get_urges_service),
    goals: GoalsService = Depends(get_goals_service),
    missions: MissionsService = Depends(get_missions_service),
    profiles: ProfileService = Depends(get_profile_service),
    llm: LLMClient = Depends(get_llm_client),
    clock: Clock = Depends(get_clock),
) -> ChatService:
    return ChatService(stats, study, urges, goals, missions, profiles, scoped(llm, "chat"), clock)


def get_chat_threads_service(
    repo: SqlAlchemyChatThreadRepository = Depends(get_chat_thread_repository),
    chat: ChatService = Depends(get_chat_service),
    encryptor: FieldEncryptor = Depends(get_field_encryptor),
    profiles: ProfileService = Depends(get_profile_service),
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
) -> ChatThreadsService:
    return ChatThreadsService(repo, chat, encryptor, profiles, settings.chat_retention_days, clock)


def get_pause_shortcuts_service(
    pauses: PausesService = Depends(get_pauses_service),
    repo: SqlAlchemyPauseRepository = Depends(get_pause_repository),
    habits: SqlAlchemyHabitRepository = Depends(get_habit_repository),
    profiles: ProfileService = Depends(get_profile_service),
    clock: Clock = Depends(get_clock),
) -> PauseShortcutsService:
    return PauseShortcutsService(pauses, repo, habits, profiles, clock)
