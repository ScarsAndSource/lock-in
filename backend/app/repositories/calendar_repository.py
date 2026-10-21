"""
Imported calendar events (migration 020).

Only title, start, end, all-day flag and kind are stored: no location, description, attendees or links,
so there is nothing sensitive to leak from a timetable import.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CalendarEventORM
from app.services.calendar_import import ParsedEvent


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    id: UUID
    user_id: UUID
    source: str
    uid: str
    title: str
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    kind: str
    kind_locked: bool
    imported_at: datetime


@dataclass(frozen=True, slots=True)
class SourceSummary:
    source: str
    events: int
    exams: int
    last_imported_at: datetime


class CalendarRepository(Protocol):
    async def replace_future(
        self, user_id: UUID, source: str, from_dt: datetime, events: Sequence[ParsedEvent], now: datetime,
    ) -> int: ...
    async def count_other_sources(self, user_id: UUID, source: str) -> int: ...
    async def list_range(
        self, user_id: UUID, start: datetime, end: datetime, kind: str | None, limit: int,
    ) -> list[CalendarEvent]: ...
    async def set_kind(self, user_id: UUID, event_id: UUID, kind: str) -> CalendarEvent | None: ...
    async def sources(self, user_id: UUID) -> list[SourceSummary]: ...
    async def delete_source(self, user_id: UUID, source: str) -> int: ...


def _to_domain(r: CalendarEventORM) -> CalendarEvent:
    return CalendarEvent(
        id=r.id, user_id=r.user_id, source=r.source, uid=r.uid, title=r.title,
        starts_at=r.starts_at, ends_at=r.ends_at, all_day=r.all_day, kind=r.kind,
        kind_locked=r.kind_locked, imported_at=r.imported_at,
    )


class SqlAlchemyCalendarRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def replace_future(
        self, user_id: UUID, source: str, from_dt: datetime, events: Sequence[ParsedEvent], now: datetime,
    ) -> int:
        """Swap this source's events from `from_dt` onward for the new set, keeping any kind the person corrected."""
        o = CalendarEventORM
        locked_rows = (await self._session.execute(
            select(o.uid, o.starts_at, o.kind).where(
                o.user_id == user_id, o.source == source, o.starts_at >= from_dt, o.kind_locked.is_(True),
            )
        )).all()
        locked = {(uid, starts): kind for uid, starts, kind in locked_rows}

        await self._session.execute(
            delete(o).where(o.user_id == user_id, o.source == source, o.starts_at >= from_dt)
        )
        rows = [
            CalendarEventORM(
                id=uuid4(), user_id=user_id, source=source, uid=e.uid, title=e.title,
                starts_at=e.starts_at, ends_at=e.ends_at, all_day=e.all_day,
                kind=locked.get((e.uid, e.starts_at), e.kind),
                kind_locked=(e.uid, e.starts_at) in locked, imported_at=now,
            )
            for e in events
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return len(rows)

    async def count_other_sources(self, user_id: UUID, source: str) -> int:
        o = CalendarEventORM
        return int((await self._session.execute(
            select(func.count()).select_from(o).where(o.user_id == user_id, o.source != source)
        )).scalar_one())

    async def list_range(
        self, user_id: UUID, start: datetime, end: datetime, kind: str | None, limit: int,
    ) -> list[CalendarEvent]:
        o = CalendarEventORM
        stmt = select(o).where(o.user_id == user_id, o.starts_at >= start, o.starts_at < end)
        if kind is not None:
            stmt = stmt.where(o.kind == kind)
        rows = (await self._session.execute(stmt.order_by(o.starts_at, o.title).limit(limit))).scalars().all()
        return [_to_domain(r) for r in rows]

    async def set_kind(self, user_id: UUID, event_id: UUID, kind: str) -> CalendarEvent | None:
        o = CalendarEventORM
        row = (await self._session.execute(
            update(o).where(o.id == event_id, o.user_id == user_id).values(kind=kind, kind_locked=True).returning(o)
        )).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def sources(self, user_id: UUID) -> list[SourceSummary]:
        o = CalendarEventORM
        exams = func.coalesce(func.sum(case((o.kind == "exam", 1), else_=0)), 0)
        rows = (await self._session.execute(
            select(o.source, func.count(), exams, func.max(o.imported_at))
            .where(o.user_id == user_id).group_by(o.source).order_by(func.max(o.imported_at).desc())
        )).all()
        return [SourceSummary(s, int(n), int(x), ts) for s, n, x, ts in rows]

    async def delete_source(self, user_id: UUID, source: str) -> int:
        o = CalendarEventORM
        result = await self._session.execute(delete(o).where(o.user_id == user_id, o.source == source))
        return result.rowcount or 0
