"""
Calendar import and exam lookup for one person. The parsing is pure (calendar_import); this adds the person's time
zone, caps, and storage. Imports are file/paste only: no URL subscriptions, so the server never fetches an address the
user typed (no SSRF surface).

Frozen contract for the merge step:
    CalendarService.upcoming_exams(user_id, today) -> list[ExamEvent]
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from uuid import UUID

from app.dates import Clock, utc_now
from app.exceptions import NotFoundError, ValidationError
from app.repositories.calendar_repository import CalendarEvent, CalendarRepository, SourceSummary
from app.services.calendar_import import KINDS, MAX_ICS_CHARS, NotCalendarError, parse_ics
from app.services.exam_awareness import ExamEvent
from app.services.profile_service import ProfileService
from app.services.task_time import zone

MAX_EVENTS_PER_USER = 5000
MAX_SOURCES = 5
EXAM_LOOKAHEAD_DAYS = 60
DEFAULT_RANGE_DAYS = 60
MAX_LIST = 500
DEFAULT_SOURCE = "calendar"


@dataclass(frozen=True, slots=True)
class ImportResult:
    source: str
    added: int
    exams: int
    skipped: int
    warnings: tuple[str, ...]


def clean_source(label: str | None) -> str:
    return " ".join((label or "").split())[:40] or DEFAULT_SOURCE


def local_midnight(day: date, tz: tzinfo) -> datetime:
    return datetime.combine(day, time(0), tzinfo=tz)


def to_exam(event: CalendarEvent, tz: tzinfo) -> ExamEvent:
    local = event.starts_at.astimezone(tz)
    return ExamEvent(
        event_id=str(event.id),
        title=event.title,
        starts_at=event.starts_at,
        all_day=event.all_day,
        day=local.date(),
        start_minute=None if event.all_day else local.hour * 60 + local.minute,
    )


class CalendarService:
    def __init__(self, repo: CalendarRepository, profiles: ProfileService, clock: Clock = utc_now):
        self._repo, self._profiles, self._clock = repo, profiles, clock

    async def _tz(self, user_id: UUID) -> tzinfo:
        return zone((await self._profiles.get(user_id)).timezone)

    async def import_ics(self, user_id: UUID, text: str, source: str | None) -> ImportResult:
        if len(text) > MAX_ICS_CHARS:
            raise ValidationError("That calendar file is too large. Export a shorter date range.")
        label = clean_source(source)
        now = self._clock()
        tz = await self._tz(user_id)
        from_dt = local_midnight(now.astimezone(tz).date(), tz)
        try:
            parsed = parse_ics(text, tz, from_dt)
        except NotCalendarError as exc:
            raise ValidationError(str(exc)) from exc

        known = await self._repo.sources(user_id)
        if label not in {s.source for s in known} and len(known) >= MAX_SOURCES:
            raise ValidationError(f"You already have {MAX_SOURCES} imported calendars. Remove one first.")
        if await self._repo.count_other_sources(user_id, label) + len(parsed.events) > MAX_EVENTS_PER_USER:
            raise ValidationError("That would store too many calendar events. Remove an old calendar first.")

        added = await self._repo.replace_future(user_id, label, from_dt, parsed.events, now)
        return ImportResult(
            source=label,
            added=added,
            exams=sum(1 for e in parsed.events if e.kind == "exam"),
            skipped=parsed.skipped,
            warnings=parsed.warnings,
        )

    async def events(
        self, user_id: UUID, start: date | None, end: date | None, kind: str | None,
    ) -> list[CalendarEvent]:
        if kind is not None and kind not in KINDS:
            raise ValidationError(f"kind must be one of {', '.join(KINDS)}.")
        tz = await self._tz(user_id)
        today = self._clock().astimezone(tz).date()
        first = start or today
        last = end or first + timedelta(days=DEFAULT_RANGE_DAYS)
        if last < first or (last - first).days > 366:
            raise ValidationError("Pick a date range of at most a year.")
        return await self._repo.list_range(
            user_id, local_midnight(first, tz), local_midnight(last + timedelta(days=1), tz), kind, MAX_LIST,
        )

    async def upcoming_exams(self, user_id: UUID, today: date, tz: tzinfo | None = None) -> list[ExamEvent]:
        """The frozen contract. Exams from the start of `today` (local) for the next EXAM_LOOKAHEAD_DAYS days."""
        zone_ = tz or await self._tz(user_id)
        found = await self._repo.list_range(
            user_id, local_midnight(today, zone_), local_midnight(today + timedelta(days=EXAM_LOOKAHEAD_DAYS), zone_), "exam", MAX_LIST,
        )
        return [to_exam(e, zone_) for e in found]

    async def set_kind(self, user_id: UUID, event_id: UUID, kind: str) -> CalendarEvent:
        if kind not in KINDS:
            raise ValidationError(f"kind must be one of {', '.join(KINDS)}.")
        updated = await self._repo.set_kind(user_id, event_id, kind)
        if updated is None:
            raise NotFoundError("No calendar event with that id.")
        return updated

    async def sources(self, user_id: UUID) -> list[SourceSummary]:
        return await self._repo.sources(user_id)

    async def delete_source(self, user_id: UUID, source: str) -> int:
        removed = await self._repo.delete_source(user_id, clean_source(source))
        if removed == 0:
            raise NotFoundError("No imported calendar with that name.")
        return removed
