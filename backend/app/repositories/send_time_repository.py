"""
Reads and writes for adaptive send time and sleep inference (migration 021).

  * send_outcomes     one settled row per sent moment: which local hour it went out, and whether it was acted on.
  * event_times       timestamps of the person's own app usage (events spine, migration 018), for settling and for
                      the "last open before the night / first open after it" sleep proxy.

Nothing here reads free text.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CompanionMomentORM, EventORM, SendOutcomeORM


@dataclass(frozen=True, slots=True)
class SentMoment:
    kind: str
    moment_date: date
    sent_at: datetime


@dataclass(frozen=True, slots=True)
class Outcome:
    kind: str
    moment_date: date
    hour: int
    acted: bool


class SendTimeRepository(Protocol):
    async def unsettled(self, user_id: UUID, since: date, before: date) -> list[SentMoment]: ...
    async def record(self, user_id: UUID, rows: Sequence[Outcome], now: datetime) -> None: ...
    async def hour_stats(self, user_id: UUID, since: date) -> dict[str, dict[int, tuple[int, int]]]: ...
    async def event_times(self, user_id: UUID, kinds: Sequence[str], start: datetime, end: datetime) -> list[datetime]: ...


class SqlAlchemySendTimeRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def unsettled(self, user_id: UUID, since: date, before: date) -> list[SentMoment]:
        """Sent moments in [since, before) that have no outcome row yet."""
        m, o = CompanionMomentORM, SendOutcomeORM
        stmt = (
            select(m.moment, m.moment_date, m.created_at)
            .outerjoin(o, and_(o.user_id == m.user_id, o.kind == m.moment, o.moment_date == m.moment_date))
            .where(
                m.user_id == user_id, m.outcome == "sent", m.moment_date >= since, m.moment_date < before,
                o.user_id.is_(None),
            )
            .order_by(m.created_at)
        )
        return [SentMoment(k, d, ts) for k, d, ts in (await self._session.execute(stmt)).all()]

    async def record(self, user_id: UUID, rows: Sequence[Outcome], now: datetime) -> None:
        if not rows:
            return
        stmt = pg_insert(SendOutcomeORM).values([
            {"user_id": user_id, "kind": r.kind, "moment_date": r.moment_date, "hour": r.hour, "acted": r.acted, "settled_at": now}
            for r in rows
        ]).on_conflict_do_nothing(index_elements=["user_id", "kind", "moment_date"])
        await self._session.execute(stmt)

    async def hour_stats(self, user_id: UUID, since: date) -> dict[str, dict[int, tuple[int, int]]]:
        """{kind: {hour: (acted, ignored)}} over the lookback window."""
        o = SendOutcomeORM
        acted = func.coalesce(func.sum(case((o.acted.is_(True), 1), else_=0)), 0)
        stmt = (
            select(o.kind, o.hour, func.count(), acted)
            .where(o.user_id == user_id, o.moment_date >= since)
            .group_by(o.kind, o.hour)
        )
        out: dict[str, dict[int, tuple[int, int]]] = {}
        for kind, hour, total, hits in (await self._session.execute(stmt)).all():
            out.setdefault(kind, {})[int(hour)] = (int(hits), int(total) - int(hits))
        return out

    async def event_times(self, user_id: UUID, kinds: Sequence[str], start: datetime, end: datetime) -> list[datetime]:
        stmt = (
            select(EventORM.ts)
            .where(EventORM.user_id == user_id, EventORM.kind.in_(list(kinds)), EventORM.ts >= start, EventORM.ts <= end)
            .order_by(EventORM.ts)
        )
        return list((await self._session.execute(stmt)).scalars().all())


async def prune_outcomes(session: AsyncSession, before: date) -> int:
    """Housekeeping for the cron job (owner connection, all users)."""
    result = await session.execute(delete(SendOutcomeORM).where(SendOutcomeORM.moment_date < before))
    return result.rowcount or 0
