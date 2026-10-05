from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.deps import get_missions_service
from app.ratelimit import rate_limit
from app.routers.mappers import consistency_out, mission_out
from app.schemas import (
    CheckpointOut, MissionCreateRequest, MissionDetailOut, MissionEndRequest, MissionOut, MissionProgressOut,
)
from app.security import get_current_user_id
from app.services.missions_service import MissionsService

router = APIRouter(prefix="/missions", tags=["missions"], dependencies=[Depends(rate_limit("api"))])


@router.post("", response_model=MissionOut, status_code=status.HTTP_201_CREATED)
async def create_mission(
    body: MissionCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: MissionsService = Depends(get_missions_service),
) -> MissionOut:
    return mission_out(await service.create(user_id, body.title, body.duration_days, body.start_date))


@router.get("", response_model=list[MissionOut])
async def list_missions(
    user_id: UUID = Depends(get_current_user_id),
    service: MissionsService = Depends(get_missions_service),
) -> list[MissionOut]:
    return [mission_out(m) for m in await service.list(user_id)]


@router.get("/active", response_model=MissionDetailOut)
async def get_active_mission(
    user_id: UUID = Depends(get_current_user_id),
    service: MissionsService = Depends(get_missions_service),
) -> MissionDetailOut:
    mission, progress, pct, items = await service.get_active_detail(user_id)
    checkpoint = progress.next_checkpoint
    return MissionDetailOut(
        mission=mission_out(mission),
        progress=MissionProgressOut(
            state=progress.state, day_number=progress.day_number, days_total=progress.days_total,
            days_left=progress.days_left, elapsed_pct=progress.elapsed_pct, phase=progress.phase,
            next_checkpoint=CheckpointOut(label=checkpoint.label, day=checkpoint.day, checkpoint_date=checkpoint.on_date)
            if checkpoint else None,
        ),
        consistency_pct=pct,
        habits=[consistency_out(i) for i in items],
    )


@router.post("/{mission_id}/end", response_model=MissionOut)
async def end_mission(
    mission_id: UUID,
    body: MissionEndRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: MissionsService = Depends(get_missions_service),
) -> MissionOut:
    """completed=true -> 'completed'; false -> 'ended_early'. Neither is a failure state."""
    return mission_out(await service.end(user_id, mission_id, body.completed))
