from __future__ import annotations

from datetime import date
from uuid import UUID

from app.dates import Clock, assert_loggable_date, utc_now
from app.domain import MoodLog
from app.exceptions import NotFoundError, ValidationError
from app.repositories.mood_repository import MoodRepository

_MAX_RANGE_DAYS = 90


class MoodService:
    def __init__(self, repo: MoodRepository, clock: Clock = utc_now):
        self._repo = repo
        self._clock = clock

    async def log_mood(self, user_id: UUID, log_date: date, valence: int, energy: int) -> MoodLog:
        assert_loggable_date(log_date, self._clock().date())
        try:
            log = MoodLog(user_id=user_id, log_date=log_date, valence=valence, energy=energy)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return await self._repo.upsert_log(log)

    async def get_log(self, user_id: UUID, log_date: date) -> MoodLog | None:
        return await self._repo.get_log(user_id, log_date)

    async def delete_log(self, user_id: UUID, log_date: date) -> None:
        if not await self._repo.delete_log(user_id, log_date):
            raise NotFoundError("No mood log for this date.")

    async def list_recent(self, user_id: UUID, start_date: date, end_date: date) -> list[MoodLog]:
        if end_date < start_date:
            raise ValidationError("end_date must not be before start_date.")
        if (end_date - start_date).days > _MAX_RANGE_DAYS:
            raise ValidationError(f"Range too large -- max {_MAX_RANGE_DAYS} days per request.")
        return await self._repo.list_logs_in_range(user_id, start_date, end_date)
