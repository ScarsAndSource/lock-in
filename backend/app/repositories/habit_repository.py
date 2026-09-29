from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import HabitDefinition, HabitLog, HabitStatus, TargetFrequency
from app.models import HabitDefinitionORM, HabitLogORM

# How far back to pull history when computing "same weekday" defaults.
# 4 occurrences of a given weekday need at most 4*7 = 28 days if every
# single one is logged; doubling that comfortably absorbs gaps (sick days,
# habit paused, etc.) without an unbounded query.
DEFAULT_HISTORY_LOOKBACK_DAYS = 60


class HabitRepository(Protocol):
    async def create_habit(
        self, user_id: UUID, name: str, target_frequency: TargetFrequency
    ) -> HabitDefinition: ...

    async def list_active_habits(self, user_id: UUID) -> list[HabitDefinition]: ...

    async def get_habit(self, user_id: UUID, habit_id: UUID) -> HabitDefinition | None: ...

    async def get_recent_logs_by_habit(
        self, user_id: UUID, habit_ids: list[UUID], before_date: date,
        lookback_days: int = DEFAULT_HISTORY_LOOKBACK_DAYS,
    ) -> dict[UUID, list[HabitLog]]: ...

    async def get_log(self, user_id: UUID, habit_id: UUID, log_date: date) -> HabitLog | None: ...

    async def upsert_log(self, log: HabitLog) -> HabitLog: ...


def _frequency_to_dict(freq: TargetFrequency) -> dict:
    if freq.type == "weekdays":
        return {"type": "weekdays", "days": list(freq.days)}
    return {"type": "n_per_week", "count": freq.count}


def _frequency_from_dict(data: dict) -> TargetFrequency:
    if data["type"] == "weekdays":
        return TargetFrequency(type="weekdays", days=tuple(data["days"]))
    return TargetFrequency(type="n_per_week", count=data["count"])


def _habit_from_orm(row: HabitDefinitionORM) -> HabitDefinition:
    return HabitDefinition(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        target_frequency=_frequency_from_dict(row.target_frequency),
        created_at=row.created_at,
        archived_at=row.archived_at,
    )


def _log_from_orm(row: HabitLogORM) -> HabitLog:
    return HabitLog(
        habit_id=row.habit_id,
        user_id=row.user_id,
        log_date=row.log_date,
        status=HabitStatus(row.status),
        note=row.note,
        is_default=row.is_default,
    )


class SqlAlchemyHabitRepository:
    """
    Every method here filters by user_id explicitly, in addition to Postgres
    RLS enforcing the same boundary at the database layer. This is
    deliberate defense-in-depth per SPEC.md's stance that the friend-group
    v1 and a public launch run the exact same code path — a single point of
    failure in access control (relying on RLS alone, or on the app layer
    alone) is not acceptable for tables holding this kind of personal data.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_habit(
        self, user_id: UUID, name: str, target_frequency: TargetFrequency
    ) -> HabitDefinition:
        now = datetime.now(timezone.utc)
        row = HabitDefinitionORM(
            user_id=user_id,
            name=name,
            target_frequency=_frequency_to_dict(target_frequency),
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _habit_from_orm(row)

    async def list_active_habits(self, user_id: UUID) -> list[HabitDefinition]:
        stmt = select(HabitDefinitionORM).where(
            HabitDefinitionORM.user_id == user_id,
            HabitDefinitionORM.archived_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return [_habit_from_orm(row) for row in result.scalars().all()]

    async def get_habit(self, user_id: UUID, habit_id: UUID) -> HabitDefinition | None:
        stmt = select(HabitDefinitionORM).where(
            HabitDefinitionORM.id == habit_id,
            HabitDefinitionORM.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _habit_from_orm(row) if row else None

    async def get_recent_logs_by_habit(
        self, user_id: UUID, habit_ids: list[UUID], before_date: date,
        lookback_days: int = DEFAULT_HISTORY_LOOKBACK_DAYS,
    ) -> dict[UUID, list[HabitLog]]:
        if not habit_ids:
            return {}

        since = before_date - timedelta(days=lookback_days)
        stmt = select(HabitLogORM).where(
            HabitLogORM.user_id == user_id,
            HabitLogORM.habit_id.in_(habit_ids),
            HabitLogORM.log_date >= since,
            HabitLogORM.log_date < before_date,
        )
        result = await self._session.execute(stmt)

        grouped: dict[UUID, list[HabitLog]] = {hid: [] for hid in habit_ids}
        for row in result.scalars().all():
            grouped[row.habit_id].append(_log_from_orm(row))
        return grouped

    async def get_log(self, user_id: UUID, habit_id: UUID, log_date: date) -> HabitLog | None:
        stmt = select(HabitLogORM).where(
            HabitLogORM.user_id == user_id,
            HabitLogORM.habit_id == habit_id,
            HabitLogORM.log_date == log_date,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _log_from_orm(row) if row else None

    async def upsert_log(self, log: HabitLog) -> HabitLog:
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(HabitLogORM)
            .values(
                habit_id=log.habit_id,
                user_id=log.user_id,
                log_date=log.log_date,
                status=log.status.value,
                note=log.note,
                is_default=log.is_default,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="habit_logs_habit_id_log_date_key",
                set_={
                    "status": log.status.value,
                    "note": log.note,
                    "is_default": log.is_default,
                    "updated_at": now,
                },
            )
            .returning(HabitLogORM)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        row = result.scalar_one()
        return _log_from_orm(row)
