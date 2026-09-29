from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import get_sleep_service
from app.domain import SleepLog
from app.exceptions import ValidationError
from app.schemas import SleepLogOut, SleepLogRequest
from app.security import get_current_user_id
from app.services.sleep_service import SleepService

router = APIRouter(prefix="/sleep", tags=["sleep"])


def _to_out(log: SleepLog) -> SleepLogOut:
    return SleepLogOut(
        log_date=log.log_date,
        time_to_bed=log.time_to_bed,
        time_woke=log.time_woke,
        self_rated_quality=log.self_rated_quality,
        duration_minutes=log.duration_minutes,
    )


@router.post("/logs", response_model=SleepLogOut, status_code=status.HTTP_200_OK)
async def log_sleep(
    body: SleepLogRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: SleepService = Depends(get_sleep_service),
) -> SleepLogOut:
    """
    Upsert keyed on (user_id, log_date) -- correcting a past night's entry
    is the same call as logging it the first time, same principle as
    habits/logs.
    """
    log = await service.log_sleep(
        user_id, body.log_date, body.time_to_bed, body.time_woke, body.self_rated_quality
    )
    return _to_out(log)


@router.get("/logs/{log_date}", response_model=SleepLogOut)
async def get_sleep_log(
    log_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: SleepService = Depends(get_sleep_service),
) -> SleepLogOut:
    log = await service.get_log(user_id, log_date)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No sleep log for this date.")
    return _to_out(log)


@router.get("/logs", response_model=list[SleepLogOut])
async def list_sleep_logs(
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: UUID = Depends(get_current_user_id),
    service: SleepService = Depends(get_sleep_service),
) -> list[SleepLogOut]:
    try:
        logs = await service.list_recent(user_id, start_date, end_date)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return [_to_out(log) for log in logs]
