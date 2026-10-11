from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import get_pauses_service, get_profile_service
from app.domain import Pause
from app.ratelimit import rate_limit
from app.schemas_friction import PauseCreateRequest, PauseOut
from app.security import get_current_user_id
from app.services.pauses_service import PausesService
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/pauses", tags=["pauses"], dependencies=[Depends(rate_limit("api"))])


def _out(p: Pause, today) -> PauseOut:
    return PauseOut(
        id=p.id,
        start_date=p.start_date,
        end_date=p.end_date,
        active=p.covers(today),
        habit_id=p.habit_id,
    )


@router.post("", response_model=PauseOut, status_code=status.HTTP_201_CREATED)
async def create_pause(
    body: PauseCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: PausesService = Depends(get_pauses_service),
    profiles: ProfileService = Depends(get_profile_service),
) -> PauseOut:
    """Sick, travelling, exam week: these days aren't counted for or against you. Add habit_id to pause just that habit. Past 30 days to 90 ahead."""
    pause = await service.create(user_id, body.start_date, body.end_date, body.habit_id)
    return _out(pause, await profiles.today(user_id))


@router.get("", response_model=list[PauseOut])
async def list_pauses(
    include_past: bool = Query(False),
    habit_id: UUID | None = Query(None, description="Only pauses for this habit."),
    user_id: UUID = Depends(get_current_user_id),
    service: PausesService = Depends(get_pauses_service),
    profiles: ProfileService = Depends(get_profile_service),
) -> list[PauseOut]:
    today = await profiles.today(user_id)
    return [_out(p, today) for p in await service.list(user_id, include_past, habit_id)]


@router.post("/{pause_id}/end", response_model=PauseOut)
async def end_pause_today(
    pause_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: PausesService = Depends(get_pauses_service),
    profiles: ProfileService = Depends(get_profile_service),
) -> PauseOut:
    """I'm back early: the pause ends today."""
    return _out(await service.end_now(user_id, pause_id), await profiles.today(user_id))


@router.delete("/{pause_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_pause(
    pause_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: PausesService = Depends(get_pauses_service),
) -> Response:
    await service.delete(user_id, pause_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
