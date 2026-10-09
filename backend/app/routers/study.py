from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import get_study_service
from app.domain import StudySession, Subject
from app.ratelimit import rate_limit
from app.schemas_tracking import (
    StudySessionOut, StudySessionRequest, StudySummaryOut, SubjectBulkRequest, SubjectCreateRequest,
    SubjectMinutesOut, SubjectOut, SubjectPatchRequest,
)
from app.security import get_current_user_id
from app.services.study_service import StudyService

router = APIRouter(prefix="/study", tags=["study"], dependencies=[Depends(rate_limit("api"))])


def _subject_out(s: Subject) -> SubjectOut:
    return SubjectOut(id=s.id, name=s.name, archived_at=s.archived_at)


def _session_out(s: StudySession, names: dict[UUID, str]) -> StudySessionOut:
    return StudySessionOut(
        id=s.id, log_date=s.log_date, subject_id=s.subject_id, subject_name=names.get(s.subject_id, "(unknown)"),
        planned_minutes=s.planned_minutes, actual_minutes=s.actual_minutes,
    )


@router.post("/subjects", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
async def create_subject(
    body: SubjectCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudyService = Depends(get_study_service),
) -> SubjectOut:
    """Idempotent: same name (any case) returns the existing subject. Powers inline '+ Create'."""
    return _subject_out(await service.create_subject(user_id, body.name))


@router.post("/subjects/bulk", response_model=list[SubjectOut], status_code=status.HTTP_201_CREATED)
async def bulk_add_subjects(
    body: SubjectBulkRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudyService = Depends(get_study_service),
) -> list[SubjectOut]:
    """Onboarding paste: {"text": "ADS, AISC, CN"}."""
    return [_subject_out(s) for s in await service.bulk_add(user_id, body.text)]


@router.get("/subjects", response_model=list[SubjectOut])
async def list_subjects(
    include_archived: bool = Query(False),
    user_id: UUID = Depends(get_current_user_id),
    service: StudyService = Depends(get_study_service),
) -> list[SubjectOut]:
    return [_subject_out(s) for s in await service.list_subjects(user_id, include_archived)]


@router.patch("/subjects/{subject_id}", response_model=SubjectOut)
async def update_subject(
    subject_id: UUID,
    body: SubjectPatchRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudyService = Depends(get_study_service),
) -> SubjectOut:
    return _subject_out(await service.update_subject(user_id, subject_id, body.name, body.archived))


@router.post("/sessions", response_model=StudySessionOut, status_code=status.HTTP_201_CREATED)
async def log_session(
    body: StudySessionRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudyService = Depends(get_study_service),
) -> StudySessionOut:
    s = await service.log_session(
        user_id, body.log_date, body.subject_id, body.subject_name, body.planned_minutes, body.actual_minutes
    )
    return _session_out(s, await service.subject_names(user_id))


@router.get("/sessions", response_model=list[StudySessionOut])
async def list_sessions(
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: UUID = Depends(get_current_user_id),
    service: StudyService = Depends(get_study_service),
) -> list[StudySessionOut]:
    names = await service.subject_names(user_id)
    return [_session_out(s, names) for s in await service.list_sessions(user_id, start_date, end_date)]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_session(
    session_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudyService = Depends(get_study_service),
) -> Response:
    await service.delete_session(user_id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/summary", response_model=StudySummaryOut)
async def study_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: UUID = Depends(get_current_user_id),
    service: StudyService = Depends(get_study_service),
) -> StudySummaryOut:
    s = await service.summary(user_id, start_date, end_date)
    by_subject = await service.breakdown(user_id, start_date, end_date)
    return StudySummaryOut(
        start_date=start_date, end_date=end_date, total_actual=s.total_actual, total_planned=s.total_planned,
        follow_through_pct=s.follow_through_pct, days_studied=s.days_studied,
        by_subject=[SubjectMinutesOut(subject_id=sid, name=name, minutes=m) for sid, name, m in by_subject],
    )
