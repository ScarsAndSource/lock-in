"""Calendar import (.ics), the imported events, and the exams the companion plans around."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dates import Clock
from app.deps import get_clock, get_db, get_profile_service
from app.ratelimit import rate_limit
from app.repositories.calendar_repository import CalendarEvent, SqlAlchemyCalendarRepository
from app.schemas_calendar import EventOut, ExamOut, ImportIn, ImportOut, KindIn, SourceOut
from app.security import get_current_user_id
from app.services.calendar_service import CalendarService
from app.services.profile_service import ProfileService
from app.services.task_time import zone

router = APIRouter(prefix="/calendar", tags=["calendar"], dependencies=[Depends(rate_limit("api"))])


def get_calendar_service(
    session: AsyncSession = Depends(get_db),
    profiles: ProfileService = Depends(get_profile_service),
    clock: Clock = Depends(get_clock),
) -> CalendarService:
    return CalendarService(SqlAlchemyCalendarRepository(session), profiles, clock)


def _event_out(e: CalendarEvent) -> EventOut:
    return EventOut(
        id=str(e.id),
        title=e.title,
        starts_at=e.starts_at,
        ends_at=e.ends_at,
        all_day=e.all_day,
        kind=e.kind,  # type: ignore[arg-type]
        kind_locked=e.kind_locked,
        source=e.source,
    )


@router.post("/import", response_model=ImportOut, dependencies=[Depends(rate_limit("calendar_import"))])
async def import_calendar(
    body: ImportIn,
    user_id: UUID = Depends(get_current_user_id),
    service: CalendarService = Depends(get_calendar_service),
) -> ImportOut:
    """Replace the future events of one imported calendar (same `source` = same calendar) with the file's contents."""
    result = await service.import_ics(user_id, body.ics, body.source)
    return ImportOut(
        source=result.source,
        added=result.added,
        exams=result.exams,
        skipped=result.skipped,
        warnings=list(result.warnings),
    )


@router.get("/events", response_model=list[EventOut])
async def list_events(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    kind: str | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
    service: CalendarService = Depends(get_calendar_service),
) -> list[EventOut]:
    return [_event_out(e) for e in await service.events(user_id, start, end, kind)]


@router.get("/exams", response_model=list[ExamOut])
async def list_exams(
    user_id: UUID = Depends(get_current_user_id),
    service: CalendarService = Depends(get_calendar_service),
    profiles: ProfileService = Depends(get_profile_service),
    clock: Clock = Depends(get_clock),
) -> list[ExamOut]:
    tz = zone((await profiles.get(user_id)).timezone)
    today = clock().astimezone(tz).date()
    return [
        ExamOut(
            id=e.event_id,
            title=e.title,
            starts_at=e.starts_at,
            all_day=e.all_day,
            day=e.day,
            days_until=e.days_until(today),
        )
        for e in await service.upcoming_exams(user_id, today, tz)
    ]


@router.patch("/events/{event_id}", response_model=EventOut)
async def set_event_kind(
    event_id: UUID,
    body: KindIn,
    user_id: UUID = Depends(get_current_user_id),
    service: CalendarService = Depends(get_calendar_service),
) -> EventOut:
    """Correct a guess ("that isn't an exam"). The correction survives re-importing the calendar."""
    return _event_out(await service.set_kind(user_id, event_id, body.kind))


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(
    user_id: UUID = Depends(get_current_user_id),
    service: CalendarService = Depends(get_calendar_service),
) -> list[SourceOut]:
    return [
        SourceOut(source=s.source, events=s.events, exams=s.exams, last_imported_at=s.last_imported_at)
        for s in await service.sources(user_id)
    ]


@router.delete("/sources/{source}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_source(
    source: str,
    user_id: UUID = Depends(get_current_user_id),
    service: CalendarService = Depends(get_calendar_service),
) -> Response:
    await service.delete_source(user_id, source)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
