from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.deps import get_mood_service
from app.ratelimit import rate_limit
from app.routers.mappers import mood_out
from app.schemas import MoodEntryIn, MoodLogOut
from app.security import get_current_user_id
from app.services.mood_service import MoodService

router = APIRouter(prefix="/mood", tags=["mood"], dependencies=[Depends(rate_limit("api"))])


@router.put("/{log_date}", response_model=MoodLogOut)
async def put_mood(
    log_date: date,
    body: MoodEntryIn,
    user_id: UUID = Depends(get_current_user_id),
    service: MoodService = Depends(get_mood_service),
) -> MoodLogOut:
    """Two taps. Upsert on (user, date): changing your mind is the same call."""
    return mood_out(await service.log_mood(user_id, log_date, body.valence, body.energy))


@router.get("/{log_date}", response_model=MoodLogOut)
async def get_mood(
    log_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: MoodService = Depends(get_mood_service),
) -> MoodLogOut:
    log = await service.get_log(user_id, log_date)
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No mood log for this date.")
    return mood_out(log)


@router.get("", response_model=list[MoodLogOut])
async def list_mood(
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: UUID = Depends(get_current_user_id),
    service: MoodService = Depends(get_mood_service),
) -> list[MoodLogOut]:
    return [mood_out(l) for l in await service.list_recent(user_id, start_date, end_date)]


@router.delete("/{log_date}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_mood(
    log_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: MoodService = Depends(get_mood_service),
) -> Response:
    await service.delete_log(user_id, log_date)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
