from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dates import Clock, utc_now
from app.db import get_db
from app.repositories.account_repository import SqlAlchemyAccountRepository
from app.repositories.checkin_repository import SqlAlchemyCheckinRepository
from app.repositories.habit_repository import SqlAlchemyHabitRepository
from app.repositories.mission_repository import SqlAlchemyMissionRepository
from app.repositories.profile_repository import SqlAlchemyProfileRepository
from app.repositories.screen_time_repository import SqlAlchemyScreenTimeRepository
from app.repositories.sleep_repository import SqlAlchemySleepRepository
from app.security import FieldEncryptor, get_field_encryptor
from app.services.account_service import AccountService
from app.services.checkins_service import CheckinsService
from app.services.habits_service import HabitsService
from app.services.missions_service import MissionsService
from app.services.profile_service import ProfileService
from app.services.screen_time_service import ScreenTimeService
from app.services.sleep_service import SleepService
from app.services.stats_service import StatsService


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
) -> CheckinsService:
    return CheckinsService(habit_repo, checkin_repo, encryptor, sleep_repo, screen_repo, clock)


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
) -> StatsService:
    return StatsService(habit_repo, sleep_repo, screen_repo, profiles)


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
