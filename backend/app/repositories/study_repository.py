from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import StudySession, Subject
from app.exceptions import ConflictError
from app.models import StudySessionORM, SubjectORM


class SubjectRepository(Protocol):
    async def create(self, user_id: UUID, name: str) -> Subject | None: ...
    async def list(self, user_id: UUID, include_archived: bool = False) -> list[Subject]: ...
    async def get(self, user_id: UUID, subject_id: UUID) -> Subject | None: ...
    async def find_by_name(self, user_id: UUID, name: str) -> Subject | None: ...
    async def update(
        self, user_id: UUID, subject_id: UUID, name: str | None, archived: bool | None, now: datetime,
    ) -> Subject | None: ...


class StudySessionRepository(Protocol):
    async def add(self, session: StudySession) -> StudySession: ...
    async def get(self, user_id: UUID, session_id: UUID) -> StudySession | None: ...
    async def delete(self, user_id: UUID, session_id: UUID) -> bool: ...
    async def list_in_range(self, user_id: UUID, start: date, end: date) -> list[StudySession]: ...


def _subject(row: SubjectORM) -> Subject:
    return Subject(id=row.id, user_id=row.user_id, name=row.name, created_at=row.created_at, archived_at=row.archived_at)


def _session(row: StudySessionORM) -> StudySession:
    return StudySession(
        id=row.id, user_id=row.user_id, subject_id=row.subject_id, log_date=row.log_date,
        actual_minutes=row.actual_minutes, planned_minutes=row.planned_minutes,
    )


class SqlAlchemySubjectRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, user_id: UUID, name: str) -> Subject | None:
        """None when an active subject with that name already exists (race-safe via a savepoint)."""
        now = datetime.now(timezone.utc)
        row = SubjectORM(id=uuid4(), user_id=user_id, name=name, created_at=now, updated_at=now)
        try:
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
        except IntegrityError:
            return None
        return _subject(row)

    async def list(self, user_id: UUID, include_archived: bool = False) -> list[Subject]:
        stmt = select(SubjectORM).where(SubjectORM.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(SubjectORM.archived_at.is_(None))
        rows = (await self._session.execute(stmt.order_by(func.lower(SubjectORM.name)))).scalars().all()
        return [_subject(r) for r in rows]

    async def get(self, user_id: UUID, subject_id: UUID) -> Subject | None:
        stmt = select(SubjectORM).where(SubjectORM.id == subject_id, SubjectORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _subject(row) if row else None

    async def find_by_name(self, user_id: UUID, name: str) -> Subject | None:
        stmt = (
            select(SubjectORM)
            .where(SubjectORM.user_id == user_id, func.lower(SubjectORM.name) == name.lower())
            .order_by(SubjectORM.archived_at.is_(None).desc())  # prefer the active one
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalars().first()
        return _subject(row) if row else None

    async def update(
        self, user_id: UUID, subject_id: UUID, name: str | None, archived: bool | None, now: datetime,
    ) -> Subject | None:
        stmt = select(SubjectORM).where(SubjectORM.id == subject_id, SubjectORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        try:
            async with self._session.begin_nested():
                if name is not None:
                    row.name = name
                if archived is True:
                    row.archived_at = now
                elif archived is False:
                    row.archived_at = None
                row.updated_at = now
                await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("You already have a subject with that name.") from exc
        return _subject(row)


class SqlAlchemyStudySessionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, session: StudySession) -> StudySession:
        now = datetime.now(timezone.utc)
        self._session.add(StudySessionORM(
            id=session.id, user_id=session.user_id, subject_id=session.subject_id, log_date=session.log_date,
            planned_minutes=session.planned_minutes, actual_minutes=session.actual_minutes,
            created_at=now, updated_at=now,
        ))
        await self._session.flush()
        return session

    async def get(self, user_id: UUID, session_id: UUID) -> StudySession | None:
        stmt = select(StudySessionORM).where(StudySessionORM.id == session_id, StudySessionORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _session(row) if row else None

    async def delete(self, user_id: UUID, session_id: UUID) -> bool:
        result = await self._session.execute(
            delete(StudySessionORM).where(StudySessionORM.id == session_id, StudySessionORM.user_id == user_id)
        )
        return (result.rowcount or 0) > 0

    async def list_in_range(self, user_id: UUID, start: date, end: date) -> list[StudySession]:
        stmt = (
            select(StudySessionORM)
            .where(StudySessionORM.user_id == user_id, StudySessionORM.log_date >= start, StudySessionORM.log_date <= end)
            .order_by(StudySessionORM.log_date, StudySessionORM.created_at)
        )
        return [_session(r) for r in (await self._session.execute(stmt)).scalars().all()]
