from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import get_screen_time_service
from app.domain import ScreenTimeLog
from app.exceptions import ValidationError
from app.schemas import ScreenTimeLogOut, ScreenTimeLogRequest
from app.security import get_current_user_id
from app.services.screen_time_service import ScreenTimeService

router = APIRouter(prefix="/screen-time", tags=["screen-time"])


def _to_out(log: ScreenTimeLog) -> ScreenTimeLogOut:
    return ScreenTimeLogOut(
        log_date=log.log_date,
        total_minutes=log.total_minutes,
        source=log.source,
        category_breakdown=log.category_breakdown,
    )


@router.post("/logs", response_model=ScreenTimeLogOut, status_code=status.HTTP_200_OK)
async def log_screen_time(
    body: ScreenTimeLogRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ScreenTimeService = Depends(get_screen_time_service),
) -> ScreenTimeLogOut:
    log = await service.log_screen_time(
        user_id, body.log_date, body.total_minutes, body.source, body.category_breakdown
    )
    return _to_out(log)


@router.get("/logs/{log_date}", response_model=ScreenTimeLogOut)
async def get_screen_time_log(
    log_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: ScreenTimeService = Depends(get_screen_time_service),
) -> ScreenTimeLogOut:
    log = await service.get_log(user_id, log_date)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No screen-time log for this date.")
    return _to_out(log)


@router.get("/logs", response_model=list[ScreenTimeLogOut])
async def list_screen_time_logs(
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: UUID = Depends(get_current_user_id),
    service: ScreenTimeService = Depends(get_screen_time_service),
) -> list[ScreenTimeLogOut]:
    try:
        logs = await service.list_recent(user_id, start_date, end_date)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return [_to_out(log) for log in logs]
