from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.deps import get_screen_time_service
from app.ratelimit import rate_limit
from app.routers.mappers import screen_out
from app.schemas import ScreenTimeLogOut, ScreenTimeLogRequest
from app.security import get_current_user_id
from app.services.screen_time_service import ScreenTimeService

router = APIRouter(prefix="/screen-time", tags=["screen-time"], dependencies=[Depends(rate_limit("api"))])


@router.post("/logs", response_model=ScreenTimeLogOut, status_code=status.HTTP_200_OK)
async def log_screen_time(
    body: ScreenTimeLogRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ScreenTimeService = Depends(get_screen_time_service),
) -> ScreenTimeLogOut:
    log = await service.log_screen_time(user_id, body.log_date, body.total_minutes, body.source, body.category_breakdown)
    return screen_out(log)


@router.get("/logs/{log_date}", response_model=ScreenTimeLogOut)
async def get_screen_time_log(
    log_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: ScreenTimeService = Depends(get_screen_time_service),
) -> ScreenTimeLogOut:
    log = await service.get_log(user_id, log_date)
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No screen-time log for this date.")
    return screen_out(log)


@router.get("/logs", response_model=list[ScreenTimeLogOut])
async def list_screen_time_logs(
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: UUID = Depends(get_current_user_id),
    service: ScreenTimeService = Depends(get_screen_time_service),
) -> list[ScreenTimeLogOut]:
    return [screen_out(l) for l in await service.list_recent(user_id, start_date, end_date)]


@router.delete("/logs/{log_date}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_screen_time_log(
    log_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: ScreenTimeService = Depends(get_screen_time_service),
) -> Response:
    await service.delete_log(user_id, log_date)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
