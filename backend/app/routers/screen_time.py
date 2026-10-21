from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from app.deps import get_media_service, get_screen_time_service
from app.ratelimit import rate_limit
from app.routers.mappers import screen_out
from app.schemas import ScreenTimeLogOut, ScreenTimeLogRequest
from app.schemas_media import ScreenshotProposalOut
from app.security import get_current_user_id
from app.services.media_service import MediaService
from app.services.screenshot_parser import MAX_IMAGE_BYTES
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


@router.post(
    "/parse-screenshot", response_model=ScreenshotProposalOut,
    dependencies=[
        Depends(rate_limit("media_minute", limit_setting="rate_limit_media_per_minute")),
        Depends(rate_limit("media_hour", limit_setting="rate_limit_media_per_hour", window_seconds=3600)),
    ],
)
async def parse_screenshot(
    image: UploadFile = File(...),
    user_id: UUID = Depends(get_current_user_id),
    service: MediaService = Depends(get_media_service),
) -> ScreenshotProposalOut:
    """A screenshot of today's Screen Time / Digital Wellbeing -> a proposal. Saves nothing: the person confirms it
    through the check-in (source "screenshot"). The file type comes from its bytes, never from what it claims."""
    data = await image.read(MAX_IMAGE_BYTES + 1)
    p = await service.parse_screenshot(data)
    return ScreenshotProposalOut(total_minutes=p.total_minutes, category_breakdown=p.categories, confidence=p.confidence)
