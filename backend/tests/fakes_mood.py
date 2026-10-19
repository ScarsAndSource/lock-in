"""In-memory mood repository for API tests (same shape as the SQLAlchemy one)."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from app.domain import MoodLog


class InMemoryMoodRepository:
    def __init__(self):
        self._logs: dict[tuple[UUID, date], MoodLog] = {}

    async def upsert_log(self, log: MoodLog) -> MoodLog:
        self._logs[(log.user_id, log.log_date)] = log
        return log

    async def get_log(self, user_id: UUID, log_date: date) -> MoodLog | None:
        return self._logs.get((user_id, log_date))

    async def list_logs_in_range(self, user_id: UUID, start_date: date, end_date: date) -> list[MoodLog]:
        return sorted(
            (l for (uid, d), l in self._logs.items() if uid == user_id and start_date <= d <= end_date),
            key=lambda l: l.log_date,
        )

    async def delete_log(self, user_id: UUID, log_date: date) -> bool:
        return self._logs.pop((user_id, log_date), None) is not None
