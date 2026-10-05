from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import get_sleep_service
from app.ratelimit import rate_limit
from app.routers.mappers import sleep_out
from app.schemas import SleepLogOut, SleepLogRequest
from app.security import get_current_user_id
from app.services.sleep_service import SleepService

router = APIRouter(prefix="/sleep", tags=["sleep"], dependencies=[Depends(rate_limit("api"))])


@router.post("/logs", response_model=SleepLogOut, status_code=status.HTTP_200_OK)
async def log_sleep(
    body: SleepLogRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: SleepService = Depends(get_sleep_service),
) -> SleepLogOut:
    """Upsert on (user, date) -- correcting a night is the same call as logging it."""
    log = await service.log_sleep(user_id, body.log_date, body.time_to_bed, body.time_woke, body.self_rated_quality)
    return sleep_out(log)


@router.get("/logs/{log_date}", response_model=SleepLogOut)
async def get_sleep_log(
    log_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: SleepService = Depends(get_sleep_service),
) -> SleepLogOut:
    log = await service.get_log(user_id, log_date)
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No sleep log for this date.")
    return sleep_out(log)


@router.get("/logs", response_model=list[SleepLogOut])
async def list_sleep_logs(
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: UUID = Depends(get_current_user_id),
    service: SleepService = Depends(get_sleep_service),
) -> list[SleepLogOut]:
    return [sleep_out(l) for l in await service.list_recent(user_id, start_date, end_date)]
