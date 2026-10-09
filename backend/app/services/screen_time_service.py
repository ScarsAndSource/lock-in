from __future__ import annotations

from datetime import date
from uuid import UUID

from app.dates import Clock, assert_loggable_date, utc_now
from app.domain import ScreenTimeLog, ScreenTimeSource
from app.exceptions import NotFoundError, ValidationError
from app.repositories.screen_time_repository import ScreenTimeRepository

_MAX_RANGE_DAYS = 90


class ScreenTimeService:
    def __init__(self, repo: ScreenTimeRepository, clock: Clock = utc_now):
        self._repo = repo
        self._clock = clock

    async def log_screen_time(
        self, user_id: UUID, log_date: date, total_minutes: int,
        source: ScreenTimeSource, category_breakdown: dict | None,
    ) -> ScreenTimeLog:
        assert_loggable_date(log_date, self._clock().date())
        return await self._repo.upsert_log(ScreenTimeLog(
            user_id=user_id, log_date=log_date, total_minutes=total_minutes, source=source,
            category_breakdown=category_breakdown, is_default=False,
        ))

    async def get_log(self, user_id: UUID, log_date: date) -> ScreenTimeLog | None:
        return await self._repo.get_log(user_id, log_date)

    async def delete_log(self, user_id: UUID, log_date: date) -> None:
        if not await self._repo.delete_log(user_id, log_date):
            raise NotFoundError("No screen-time log for this date.")

    async def list_recent(self, user_id: UUID, start_date: date, end_date: date) -> list[ScreenTimeLog]:
        if end_date < start_date:
            raise ValidationError("end_date must not be before start_date.")
        if (end_date - start_date).days > _MAX_RANGE_DAYS:
            raise ValidationError(f"Range too large -- max {_MAX_RANGE_DAYS} days per request.")
        return await self._repo.list_logs_in_range(user_id, start_date, end_date)
