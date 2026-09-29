from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.domain import DailyCheckin, HabitDefinition, HabitLog, ScreenTimeLog, ScreenTimeSource, SleepLog, TargetFrequency


class InMemoryHabitRepository:
    """
    Implements the same interface as SqlAlchemyHabitRepository, backed by
    plain dicts. Used to test services and routers end-to-end without a
    real Postgres instance — this is what makes the "cross-user access is
    blocked" and "opt-out defaults actually get proposed and persisted
    correctly" tests possible to run in this sandbox at all.
    """

    def __init__(self):
        self._habits: dict[UUID, HabitDefinition] = {}
        self._logs: dict[tuple[UUID, date], HabitLog] = {}  # key: (habit_id, log_date)

    async def create_habit(
        self, user_id: UUID, name: str, target_frequency: TargetFrequency
    ) -> HabitDefinition:
        habit = HabitDefinition(
            id=uuid4(),
            user_id=user_id,
            name=name,
            target_frequency=target_frequency,
            created_at=datetime.now(timezone.utc),
        )
        self._habits[habit.id] = habit
        return habit

    async def list_active_habits(self, user_id: UUID) -> list[HabitDefinition]:
        return [h for h in self._habits.values() if h.user_id == user_id and h.is_active]

    async def get_habit(self, user_id: UUID, habit_id: UUID) -> HabitDefinition | None:
        habit = self._habits.get(habit_id)
        if habit is None or habit.user_id != user_id:
            return None
        return habit

    async def get_recent_logs_by_habit(
        self, user_id: UUID, habit_ids: list[UUID], before_date: date,
        lookback_days: int = 60,
    ) -> dict[UUID, list[HabitLog]]:
        since = before_date - timedelta(days=lookback_days)
        grouped: dict[UUID, list[HabitLog]] = {hid: [] for hid in habit_ids}
        for (habit_id, log_date), log in self._logs.items():
            if (
                habit_id in grouped
                and log.user_id == user_id
                and since <= log_date < before_date
            ):
                grouped[habit_id].append(log)
        return grouped

    async def get_log(self, user_id: UUID, habit_id: UUID, log_date: date) -> HabitLog | None:
        log = self._logs.get((habit_id, log_date))
        if log is None or log.user_id != user_id:
            return None
        return log

    async def upsert_log(self, log: HabitLog) -> HabitLog:
        self._logs[(log.habit_id, log.log_date)] = log
        return log


class InMemoryCheckinRepository:
    def __init__(self):
        self._checkins: dict[tuple[UUID, date], DailyCheckin] = {}

    async def get(self, user_id: UUID, checkin_date: date) -> DailyCheckin | None:
        checkin = self._checkins.get((user_id, checkin_date))
        return checkin

    async def upsert(self, checkin: DailyCheckin) -> DailyCheckin:
        self._checkins[(checkin.user_id, checkin.checkin_date)] = checkin
        return checkin


class InMemorySleepRepository:
    def __init__(self):
        self._logs: dict[tuple[UUID, date], SleepLog] = {}

    async def upsert_log(self, log: SleepLog) -> SleepLog:
        self._logs[(log.user_id, log.log_date)] = log
        return log

    async def get_log(self, user_id: UUID, log_date: date) -> SleepLog | None:
        return self._logs.get((user_id, log_date))

    async def list_logs_in_range(
        self, user_id: UUID, start_date: date, end_date: date
    ) -> list[SleepLog]:
        return sorted(
            [l for (uid, d), l in self._logs.items() if uid == user_id and start_date <= d <= end_date],
            key=lambda l: l.log_date,
        )


class InMemoryScreenTimeRepository:
    def __init__(self):
        self._logs: dict[tuple[UUID, date], ScreenTimeLog] = {}

    async def upsert_log(self, log: ScreenTimeLog) -> ScreenTimeLog:
        self._logs[(log.user_id, log.log_date)] = log
        return log

    async def get_log(self, user_id: UUID, log_date: date) -> ScreenTimeLog | None:
        return self._logs.get((user_id, log_date))

    async def list_logs_in_range(
        self, user_id: UUID, start_date: date, end_date: date
    ) -> list[ScreenTimeLog]:
        return sorted(
            [l for (uid, d), l in self._logs.items() if uid == user_id and start_date <= d <= end_date],
            key=lambda l: l.log_date,
        )
