from __future__ import annotations

from datetime import date, time
from uuid import UUID

from app.domain import SleepLog
from app.exceptions import ValidationError
from app.repositories.sleep_repository import SleepRepository

# Keeps dashboard-range queries bounded -- same rationale as
# defaults_service's DEFAULT_HISTORY_LOOKBACK_DAYS: no unbounded query
# shape reachable from client input.
_MAX_RANGE_DAYS = 90


class SleepService:
    def __init__(self, repo: SleepRepository):
        self._repo = repo

    async def log_sleep(
        self,
        user_id: UUID,
        log_date: date,
        time_to_bed: time | None,
        time_woke: time | None,
        self_rated_quality: int | None,
    ) -> SleepLog:
        log = SleepLog(
            user_id=user_id,
            log_date=log_date,
            time_to_bed=time_to_bed,
            time_woke=time_woke,
            self_rated_quality=self_rated_quality,
        )
        return await self._repo.upsert_log(log)

    async def get_log(self, user_id: UUID, log_date: date) -> SleepLog | None:
        return await self._repo.get_log(user_id, log_date)

    async def list_recent(
        self, user_id: UUID, start_date: date, end_date: date
    ) -> list[SleepLog]:
        if end_date < start_date:
            raise ValidationError("end_date must not be before start_date.")
        if (end_date - start_date).days > _MAX_RANGE_DAYS:
            raise ValidationError(f"Range too large -- max {_MAX_RANGE_DAYS} days per request.")
        return await self._repo.list_logs_in_range(user_id, start_date, end_date)
