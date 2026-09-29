from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.repositories.checkin_repository import SqlAlchemyCheckinRepository
from app.repositories.habit_repository import SqlAlchemyHabitRepository
from app.repositories.screen_time_repository import SqlAlchemyScreenTimeRepository
from app.repositories.sleep_repository import SqlAlchemySleepRepository
from app.security import FieldEncryptor, get_field_encryptor
from app.services.checkins_service import CheckinsService
from app.services.habits_service import HabitsService
from app.services.screen_time_service import ScreenTimeService
from app.services.sleep_service import SleepService


def get_habit_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyHabitRepository:
    return SqlAlchemyHabitRepository(session)


def get_checkin_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyCheckinRepository:
    return SqlAlchemyCheckinRepository(session)


def get_habits_service(
    habit_repo: SqlAlchemyHabitRepository = Depends(get_habit_repository),
) -> HabitsService:
    return HabitsService(habit_repo)


def get_checkins_service(
    habit_repo: SqlAlchemyHabitRepository = Depends(get_habit_repository),
    checkin_repo: SqlAlchemyCheckinRepository = Depends(get_checkin_repository),
    encryptor: FieldEncryptor = Depends(get_field_encryptor),
) -> CheckinsService:
    return CheckinsService(habit_repo, checkin_repo, encryptor)


def get_sleep_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemySleepRepository:
    return SqlAlchemySleepRepository(session)


def get_screen_time_repository(session: AsyncSession = Depends(get_db)) -> SqlAlchemyScreenTimeRepository:
    return SqlAlchemyScreenTimeRepository(session)


def get_sleep_service(
    repo: SqlAlchemySleepRepository = Depends(get_sleep_repository),
) -> SleepService:
    return SleepService(repo)


def get_screen_time_service(
    repo: SqlAlchemyScreenTimeRepository = Depends(get_screen_time_repository),
) -> ScreenTimeService:
    return ScreenTimeService(repo)
