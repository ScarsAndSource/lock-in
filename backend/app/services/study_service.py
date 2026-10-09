"""
Study: per-user subjects (empty by default, inline create) + planned-vs-actual sessions.

follow_through_pct only looks at sessions that HAD a plan, and caps each session at its own plan
(min(actual, planned)), so a 3-hour session on one subject can't hide skipping another.
Constructed without repos it behaves like the old stub (empty summary), so nothing else breaks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from app.dates import Clock, assert_loggable_date, utc_now
from app.domain import StudySession, Subject
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.repositories.study_repository import StudySessionRepository, SubjectRepository

MAX_ACTIVE_SUBJECTS = 50
MAX_BULK_ADD = 30
MAX_RANGE_DAYS = 90
MAX_NAME_LEN = 80
MAX_MINUTES_PER_DAY = 1440


@dataclass(slots=True)
class StudySummary:
    total_actual: int = 0
    total_planned: int = 0
    follow_through_pct: float | None = None
    days_studied: int = 0


def clean_subject_name(raw: str) -> str:
    name = " ".join(raw.replace("<", "").replace(">", "").split())
    if not name:
        raise ValidationError("Subject name can't be blank.")
    if len(name) > MAX_NAME_LEN:
        raise ValidationError(f"Subject name is too long (max {MAX_NAME_LEN} characters).")
    return name


def parse_subject_list(text: str) -> list[str]:
    """'ADS, AISC\\nCN' -> ['ADS', 'AISC', 'CN']. Case-insensitive de-dupe, order kept."""
    seen: set[str] = set()
    names: list[str] = []
    for part in re.split(r"[,\n;]", text):
        if not part.strip():
            continue
        name = clean_subject_name(part)
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names


def _check_range(start: date, end: date) -> None:
    if end < start:
        raise ValidationError("end_date must not be before start_date.")
    if (end - start).days > MAX_RANGE_DAYS:
        raise ValidationError(f"Range too large -- max {MAX_RANGE_DAYS} days per request.")


class StudyService:
    def __init__(
        self, subjects: SubjectRepository | None = None, sessions: StudySessionRepository | None = None,
        clock: Clock = utc_now,
    ):
        self._subjects = subjects
        self._sessions = sessions
        self._clock = clock

    def _need(self) -> None:
        if self._subjects is None or self._sessions is None:
            raise RuntimeError("StudyService is not wired to repositories.")

    # ---------------------------------------------------------------- subjects
    async def create_subject(self, user_id: UUID, name: str) -> Subject:
        """Idempotent: same name (any case) returns the existing subject; an archived one is revived."""
        self._need()
        name = clean_subject_name(name)
        existing = await self._subjects.find_by_name(user_id, name)
        if existing is not None and existing.is_active:
            return existing
        if len(await self._subjects.list(user_id, include_archived=False)) >= MAX_ACTIVE_SUBJECTS:
            raise ValidationError(f"You can have at most {MAX_ACTIVE_SUBJECTS} active subjects.")
        if existing is not None:
            revived = await self._subjects.update(user_id, existing.id, None, False, self._clock())
            assert revived is not None
            return revived
        created = await self._subjects.create(user_id, name)
        if created is not None:
            return created
        again = await self._subjects.find_by_name(user_id, name)  # lost a race with ourselves
        if again is None:
            raise ConflictError("Couldn't create that subject, try again.")
        return again

    async def bulk_add(self, user_id: UUID, text: str) -> list[Subject]:
        names = parse_subject_list(text)
        if not names:
            raise ValidationError("No subject names found.")
        if len(names) > MAX_BULK_ADD:
            raise ValidationError(f"Add at most {MAX_BULK_ADD} subjects at once.")
        return [await self.create_subject(user_id, n) for n in names]

    async def list_subjects(self, user_id: UUID, include_archived: bool = False) -> list[Subject]:
        self._need()
        return await self._subjects.list(user_id, include_archived)

    async def subject_names(self, user_id: UUID) -> dict[UUID, str]:
        return {s.id: s.name for s in await self.list_subjects(user_id, include_archived=True)}

    async def update_subject(
        self, user_id: UUID, subject_id: UUID, name: str | None, archived: bool | None
    ) -> Subject:
        self._need()
        clean = clean_subject_name(name) if name is not None else None
        updated = await self._subjects.update(user_id, subject_id, clean, archived, self._clock())
        if updated is None:
            raise NotFoundError(f"No subject {subject_id} for this user.")
        return updated

    # ---------------------------------------------------------------- sessions
    async def log_session(
        self, user_id: UUID, log_date: date, subject_id: UUID | None, subject_name: str | None,
        planned_minutes: int | None, actual_minutes: int,
    ) -> StudySession:
        self._need()
        assert_loggable_date(log_date, self._clock().date())
        if (subject_id is None) == (subject_name is None):
            raise ValidationError("Give exactly one of subject_id or subject_name.")
        if planned_minutes is not None and not 1 <= planned_minutes <= MAX_MINUTES_PER_DAY:
            raise ValidationError("planned_minutes must be between 1 and 1440.")
        if not 0 <= actual_minutes <= MAX_MINUTES_PER_DAY:
            raise ValidationError("actual_minutes must be between 0 and 1440.")

        if subject_id is not None:
            subject = await self._subjects.get(user_id, subject_id)
            if subject is None:
                raise NotFoundError(f"No subject {subject_id} for this user.")
            if not subject.is_active:
                raise ValidationError("That subject is archived. Unarchive it or log under another one.")
        else:
            subject = await self.create_subject(user_id, subject_name)  # inline "+ Create 'X'"

        already = sum(s.actual_minutes for s in await self._sessions.list_in_range(user_id, log_date, log_date))
        if already + actual_minutes > MAX_MINUTES_PER_DAY:
            raise ValidationError("That would put you over 24 hours of study for one day.")

        return await self._sessions.add(StudySession(
            id=uuid4(), user_id=user_id, subject_id=subject.id, log_date=log_date,
            actual_minutes=actual_minutes, planned_minutes=planned_minutes,
        ))

    async def list_sessions(self, user_id: UUID, start: date, end: date) -> list[StudySession]:
        self._need()
        _check_range(start, end)
        return await self._sessions.list_in_range(user_id, start, end)

    async def delete_session(self, user_id: UUID, session_id: UUID) -> None:
        self._need()
        if not await self._sessions.delete(user_id, session_id):
            raise NotFoundError("No study session found for this user.")

    # ---------------------------------------------------------------- numbers
    async def summary(self, user_id: UUID, start: date, end: date) -> StudySummary:
        if self._sessions is None:
            return StudySummary()
        _check_range(start, end)
        rows = await self._sessions.list_in_range(user_id, start, end)
        planned_rows = [s for s in rows if s.planned_minutes]
        planned = sum(s.planned_minutes for s in planned_rows)
        delivered = sum(min(s.actual_minutes, s.planned_minutes) for s in planned_rows)
        return StudySummary(
            total_actual=sum(s.actual_minutes for s in rows),
            total_planned=planned,
            follow_through_pct=round(100.0 * delivered / planned, 1) if planned else None,
            days_studied=len({s.log_date for s in rows if s.actual_minutes > 0}),
        )

    async def breakdown(self, user_id: UUID, start: date, end: date) -> list[tuple[UUID, str, int]]:
        """[(subject_id, name, actual_minutes)] biggest first."""
        rows = await self.list_sessions(user_id, start, end)
        names = await self.subject_names(user_id)
        totals: dict[UUID, int] = {}
        for s in rows:
            totals[s.subject_id] = totals.get(s.subject_id, 0) + s.actual_minutes
        return sorted(((sid, names.get(sid, "(unknown)"), m) for sid, m in totals.items()), key=lambda t: -t[2])
