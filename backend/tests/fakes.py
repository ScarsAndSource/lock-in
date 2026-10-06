from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.domain import (
    DailyCheckin, HabitDefinition, HabitLog, Mission, MissionStatus, Profile,
    ScreenTimeLog, SleepLog, TargetFrequency, WeeklyRetro,
)
from app.repositories.account_repository import json_safe


class InMemoryHabitRepository:
    def __init__(self):
        self._habits: dict[UUID, HabitDefinition] = {}
        self._logs: dict[tuple[UUID, date], HabitLog] = {}  # (habit_id, log_date)

    async def create_habit(self, user_id: UUID, name: str, target_frequency: TargetFrequency) -> HabitDefinition:
        habit = HabitDefinition(
            id=uuid4(), user_id=user_id, name=name,
            target_frequency=target_frequency, created_at=datetime.now(timezone.utc),
        )
        self._habits[habit.id] = habit
        return habit

    async def list_active_habits(self, user_id: UUID) -> list[HabitDefinition]:
        return [h for h in self._habits.values() if h.user_id == user_id and h.is_active]

    async def list_habits(self, user_id: UUID, include_archived: bool = False) -> list[HabitDefinition]:
        return [h for h in self._habits.values() if h.user_id == user_id and (include_archived or h.is_active)]

    async def get_habit(self, user_id: UUID, habit_id: UUID) -> HabitDefinition | None:
        habit = self._habits.get(habit_id)
        return habit if habit is not None and habit.user_id == user_id else None

    async def update_habit(self, user_id, habit_id, name, archived, now) -> HabitDefinition | None:
        habit = await self.get_habit(user_id, habit_id)
        if habit is None:
            return None
        if name is not None:
            habit.name = name
        if archived is True:
            habit.archived_at = now
        elif archived is False:
            habit.archived_at = None
        return habit

    async def get_recent_logs_by_habit(
        self, user_id: UUID, habit_ids: list[UUID], before_date: date, lookback_days: int = 60,
    ) -> dict[UUID, list[HabitLog]]:
        since = before_date - timedelta(days=lookback_days)
        grouped: dict[UUID, list[HabitLog]] = {hid: [] for hid in habit_ids}
        for (habit_id, log_date), log in self._logs.items():
            if habit_id in grouped and log.user_id == user_id and since <= log_date < before_date:
                grouped[habit_id].append(log)
        return grouped

    async def get_logs_in_range(self, user_id, habit_ids, start_date, end_date) -> list[HabitLog]:
        wanted = set(habit_ids)
        return [
            log for (habit_id, d), log in self._logs.items()
            if habit_id in wanted and log.user_id == user_id and start_date <= d <= end_date
        ]

    async def get_log(self, user_id: UUID, habit_id: UUID, log_date: date) -> HabitLog | None:
        log = self._logs.get((habit_id, log_date))
        return log if log is not None and log.user_id == user_id else None

    async def upsert_log(self, log: HabitLog) -> HabitLog:
        self._logs[(log.habit_id, log.log_date)] = log
        return log


class InMemoryCheckinRepository:
    def __init__(self):
        self._checkins: dict[tuple[UUID, date], DailyCheckin] = {}

    async def get(self, user_id: UUID, checkin_date: date) -> DailyCheckin | None:
        return self._checkins.get((user_id, checkin_date))

    async def upsert(self, checkin: DailyCheckin) -> DailyCheckin:
        self._checkins[(checkin.user_id, checkin.checkin_date)] = checkin
        return checkin


class _RangeLogRepo:
    def __init__(self):
        self._logs: dict[tuple[UUID, date], object] = {}

    async def upsert_log(self, log):
        self._logs[(log.user_id, log.log_date)] = log
        return log

    async def get_log(self, user_id: UUID, log_date: date):
        return self._logs.get((user_id, log_date))

    async def list_logs_in_range(self, user_id: UUID, start_date: date, end_date: date):
        return sorted(
            [l for (uid, d), l in self._logs.items() if uid == user_id and start_date <= d <= end_date],
            key=lambda l: l.log_date,
        )


class InMemorySleepRepository(_RangeLogRepo):
    pass


class InMemoryScreenTimeRepository(_RangeLogRepo):
    pass


class InMemoryProfileRepository:
    def __init__(self):
        self._profiles: dict[UUID, Profile] = {}

    async def get_or_create(self, user_id: UUID) -> Profile:
        return self._profiles.setdefault(user_id, Profile(user_id=user_id, timezone="UTC", tone_preference="direct"))

    async def set_timezone(self, user_id: UUID, tz_name: str) -> Profile:
        profile = await self.get_or_create(user_id)
        profile.timezone = tz_name
        return profile


class InMemoryMissionRepository:
    def __init__(self):
        self._missions: dict[UUID, Mission] = {}

    async def create(self, mission: Mission) -> Mission:
        self._missions[mission.id] = mission
        return mission

    async def get(self, user_id: UUID, mission_id: UUID) -> Mission | None:
        m = self._missions.get(mission_id)
        return m if m is not None and m.user_id == user_id else None

    async def get_active(self, user_id: UUID) -> Mission | None:
        for m in self._missions.values():
            if m.user_id == user_id and m.status == MissionStatus.ACTIVE:
                return m
        return None

    async def list(self, user_id: UUID) -> list[Mission]:
        return sorted([m for m in self._missions.values() if m.user_id == user_id], key=lambda m: m.start_date, reverse=True)

    async def set_status(self, user_id, mission_id, status, ended_at) -> Mission | None:
        m = await self.get(user_id, mission_id)
        if m is None:
            return None
        m.status, m.ended_at = status, ended_at
        return m


class InMemoryRetroRepository:
    def __init__(self):
        self._retros: dict[UUID, WeeklyRetro] = {}

    async def create(self, retro: WeeklyRetro) -> WeeklyRetro | None:
        if await self.get_by_week(retro.user_id, retro.week_start) is not None:
            return None
        self._retros[retro.id] = retro
        return retro

    async def get_by_week(self, user_id: UUID, week_start: date) -> WeeklyRetro | None:
        return next(
            (r for r in self._retros.values() if r.user_id == user_id and r.week_start == week_start), None
        )

    async def list(self, user_id: UUID, limit: int) -> list[WeeklyRetro]:
        rows = [r for r in self._retros.values() if r.user_id == user_id]
        return sorted(rows, key=lambda r: r.week_start, reverse=True)[:limit]

    async def latest(self, user_id: UUID) -> WeeklyRetro | None:
        rows = await self.list(user_id, 1)
        return rows[0] if rows else None

    async def mark_completed(self, user_id: UUID, retro_id: UUID, now: datetime) -> WeeklyRetro | None:
        r = self._retros.get(retro_id)
        if r is None or r.user_id != user_id:
            return None
        r.completed_at = now
        return r


class InMemoryAccountRepository:
    """Reads/deletes straight out of the other fakes' private stores (test-only)."""

    def __init__(self, habits, checkins, sleep, screen, missions, profiles, retros):
        self._h, self._c, self._s, self._sc = habits, checkins, sleep, screen
        self._m, self._p, self._ret = missions, profiles, retros

    @staticmethod
    def _row(obj) -> dict:
        return {k: json_safe(v) for k, v in asdict(obj).items()}

    async def export(self, user_id: UUID) -> dict[str, list[dict]]:
        return {
            "profiles": [self._row(p) for uid, p in self._p._profiles.items() if uid == user_id],
            "habit_definitions": [self._row(h) for h in self._h._habits.values() if h.user_id == user_id],
            "habit_logs": [self._row(l) for l in self._h._logs.values() if l.user_id == user_id],
            "daily_checkins": [self._row(c) for (uid, _), c in self._c._checkins.items() if uid == user_id],
            "sleep_logs": [self._row(l) for (uid, _), l in self._s._logs.items() if uid == user_id],
            "screen_time_logs": [self._row(l) for (uid, _), l in self._sc._logs.items() if uid == user_id],
            "missions": [self._row(m) for m in self._m._missions.values() if m.user_id == user_id],
            "weekly_retros": [self._row(r) for r in self._ret._retros.values() if r.user_id == user_id],
        }

    async def delete_everything(self, user_id: UUID) -> dict[str, int]:
        def purge(store: dict, owner) -> int:
            keys = [k for k, v in store.items() if owner(k, v) == user_id]
            for k in keys:
                del store[k]
            return len(keys)

        return {
            "habit_logs": purge(self._h._logs, lambda k, v: v.user_id),
            "daily_checkins": purge(self._c._checkins, lambda k, v: v.user_id),
            "sleep_logs": purge(self._s._logs, lambda k, v: v.user_id),
            "screen_time_logs": purge(self._sc._logs, lambda k, v: v.user_id),
            "missions": purge(self._m._missions, lambda k, v: v.user_id),
            "weekly_retros": purge(self._ret._retros, lambda k, v: v.user_id),
            "habit_definitions": purge(self._h._habits, lambda k, v: v.user_id),
            "profiles": purge(self._p._profiles, lambda k, v: v.user_id),
        }

