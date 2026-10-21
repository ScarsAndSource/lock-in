"""
Ledger of actionable pushes that were sent (migration 016) AND
the companion spine events/moments (migration 018).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CompanionPush
from app.domain_companion import Observations
from app.models import (
    CompanionMomentORM,
    CompanionPushORM,
    DailyCheckinORM,
    EventORM,
    SleepLogORM,
    UrgeLogORM,
)


class CompanionRepository(Protocol):
    # Actionable push ledger
    async def reserve(self, push: CompanionPush) -> bool: ...                       # False = key already used
    async def release(self, user_id: UUID, push_id: UUID) -> None: ...
    async def list_since(self, user_id: UUID, since: datetime) -> list[CompanionPush]: ...
    async def mark_acted(self, user_id: UUID, push_id: UUID, action: str, now: datetime) -> CompanionPush | None: ...
    async def prune(self, user_id: UUID, before: datetime) -> int: ...

    # Spine events & moments
    async def add_event(self, user_id: UUID, kind: str, ref: str | None, now: datetime) -> None: ...
    async def observations(self, user_id: UUID, tz: ZoneInfo, now: datetime, days: int) -> Observations: ...
    async def moments_today(self, user_id: UUID, day: date) -> set[str]: ...
    async def mark_moment(self, user_id: UUID, day: date, moment: str, outcome: str, now: datetime) -> bool: ...


def _to_domain(row: CompanionPushORM) -> CompanionPush:
    return CompanionPush(
        id=row.id, user_id=row.user_id, kind=row.kind, key=row.key, local_date=row.local_date,
        sent_at=row.sent_at, acted_at=row.acted_at, action=row.action,
    )


def _minute(t) -> int:
    return t.hour * 60 + t.minute


class SqlAlchemyCompanionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    # ------------------------------------------------------------- push ledger
    async def reserve(self, push: CompanionPush) -> bool:
        stmt = (
            pg_insert(CompanionPushORM)
            .values(
                id=push.id, user_id=push.user_id, kind=push.kind, key=push.key, local_date=push.local_date,
                sent_at=push.sent_at,
            )
            .on_conflict_do_nothing(constraint="companion_pushes_user_key")
            .returning(CompanionPushORM.id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def release(self, user_id: UUID, push_id: UUID) -> None:
        await self._session.execute(
            delete(CompanionPushORM).where(CompanionPushORM.user_id == user_id, CompanionPushORM.id == push_id)
        )

    async def list_since(self, user_id: UUID, since: datetime) -> list[CompanionPush]:
        stmt = (
            select(CompanionPushORM)
            .where(CompanionPushORM.user_id == user_id, CompanionPushORM.sent_at >= since)
            .order_by(CompanionPushORM.sent_at)
        )
        return [_to_domain(r) for r in (await self._session.execute(stmt)).scalars().all()]

    async def mark_acted(self, user_id: UUID, push_id: UUID, action: str, now: datetime) -> CompanionPush | None:
        stmt = (
            update(CompanionPushORM)
            .where(
                CompanionPushORM.id == push_id, CompanionPushORM.user_id == user_id,
                CompanionPushORM.acted_at.is_(None),
            )
            .values(acted_at=now, action=action[:32])
            .returning(CompanionPushORM)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def prune(self, user_id: UUID, before: datetime) -> int:
        result = await self._session.execute(
            delete(CompanionPushORM).where(CompanionPushORM.user_id == user_id, CompanionPushORM.sent_at < before)
        )
        return result.rowcount or 0

    # ------------------------------------------------------------- spine events & moments
    async def add_event(self, user_id: UUID, kind: str, ref: str | None, now: datetime) -> None:
        self._session.add(EventORM(user_id=user_id, ts=now, kind=kind, ref=ref, meta={}))
        await self._session.flush()

    async def observations(self, user_id: UUID, tz: ZoneInfo, now: datetime, days: int) -> Observations:
        """Four small indexed reads. Only what the person did themselves counts (defaulted sleep rows are guesses)."""
        since = now - timedelta(days=days)
        since_date = since.astimezone(tz).date()

        sleep_rows = (await self._session.execute(
            select(SleepLogORM.time_to_bed, SleepLogORM.time_woke).where(
                SleepLogORM.user_id == user_id, SleepLogORM.log_date >= since_date, SleepLogORM.is_default.is_(False),
            )
        )).all()
        wake = tuple(_minute(woke) for _, woke in sleep_rows if woke is not None)
        bed = tuple(_minute(b) for b, _ in sleep_rows if b is not None)

        checkin_rows = (await self._session.execute(
            select(DailyCheckinORM.checkin_date, DailyCheckinORM.confirmed_at).where(
                DailyCheckinORM.user_id == user_id, DailyCheckinORM.checkin_date >= since_date,
                DailyCheckinORM.confirmed_at.is_not(None),
            )
        )).all()
        checkins: list[int] = []
        for checkin_date, confirmed_at in checkin_rows:
            local = confirmed_at.astimezone(tz)
            if 0 <= (local.date() - checkin_date).days <= 1:   # a check-in backfilled days later says nothing about habits
                checkins.append(_minute(local))

        open_rows = (await self._session.execute(
            select(EventORM.ts).where(
                EventORM.user_id == user_id, EventORM.kind == "app_open", EventORM.ts >= since,
            ).order_by(EventORM.ts)
        )).scalars().all()
        first_open: dict[date, int] = {}
        for ts in open_rows:
            local = ts.astimezone(tz)
            first_open.setdefault(local.date(), _minute(local))   # ascending, so the first one per day wins

        urge_rows = (await self._session.execute(
            select(UrgeLogORM.occurred_at, UrgeLogORM.outcome).where(
                UrgeLogORM.user_id == user_id, UrgeLogORM.occurred_at >= since,
            )
        )).all()
        urges = tuple((_minute(occurred.astimezone(tz)), outcome == "relapsed") for occurred, outcome in urge_rows)

        return Observations(
            wake_minutes=wake, bed_minutes=bed, checkin_minutes=tuple(checkins),
            first_open_minutes=tuple(first_open.values()), urges=urges,
        )

    async def moments_today(self, user_id: UUID, day: date) -> set[str]:
        rows = (await self._session.execute(
            select(CompanionMomentORM.moment).where(
                CompanionMomentORM.user_id == user_id, CompanionMomentORM.moment_date == day,
            )
        )).scalars().all()
        return set(rows)

    async def mark_moment(self, user_id: UUID, day: date, moment: str, outcome: str, now: datetime) -> bool:
        """True when this call recorded the moment, False when it was already recorded (so it never fires twice)."""
        stmt = pg_insert(CompanionMomentORM).values(
            user_id=user_id, moment_date=day, moment=moment, outcome=outcome, created_at=now,
        ).on_conflict_do_nothing(index_elements=["user_id", "moment_date", "moment"])
        result = await self._session.execute(stmt)
        return (result.rowcount or 0) > 0


async def prune_events(session: AsyncSession, before: datetime) -> int:
    """Housekeeping for the cron job (owner connection, all users): events older than `before` are not needed."""
    result = await session.execute(delete(EventORM).where(EventORM.ts < before))
    return result.rowcount or 0
