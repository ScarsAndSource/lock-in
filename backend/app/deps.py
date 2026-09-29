from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.repositories.checkin_repository import SqlAlchemyCheckinRepository
from app.repositories.habit_repository import SqlAlchemyHabitRepository
from app.security import FieldEncryptor, get_field_encryptor
from app.services.checkins_service import CheckinsService
from app.services.habits_service import HabitsService


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
