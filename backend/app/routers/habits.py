from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import get_habits_service
from app.domain import TargetFrequency
from app.ratelimit import rate_limit
from app.routers.mappers import habit_out
from app.schemas import HabitCreateRequest, HabitLogOut, HabitLogRequest, HabitOut, HabitPatchRequest
from app.security import get_current_user_id
from app.services.habits_service import HabitsService

router = APIRouter(prefix="/habits", tags=["habits"], dependencies=[Depends(rate_limit("api"))])


def _to_domain_frequency(payload) -> TargetFrequency:
    if payload.type == "weekdays":
        return TargetFrequency(type="weekdays", days=tuple(payload.days))
    return TargetFrequency(type="n_per_week", count=payload.count)


@router.post("", response_model=HabitOut, status_code=status.HTTP_201_CREATED)
async def create_habit(
    body: HabitCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: HabitsService = Depends(get_habits_service),
) -> HabitOut:
    habit = await service.create_habit(user_id, body.name, _to_domain_frequency(body.target_frequency))
    return habit_out(habit)


@router.get("", response_model=list[HabitOut])
async def list_habits(
    include_archived: bool = Query(False),
    user_id: UUID = Depends(get_current_user_id),
    service: HabitsService = Depends(get_habits_service),
) -> list[HabitOut]:
    return [habit_out(h) for h in await service.list_habits(user_id, include_archived)]


@router.patch("/{habit_id}", response_model=HabitOut)
async def update_habit(
    habit_id: UUID,
    body: HabitPatchRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: HabitsService = Depends(get_habits_service),
) -> HabitOut:
    """Rename, archive/unarchive, and/or change the schedule. Past logs are kept; consistency
    for past windows is read under the CURRENT schedule."""
    freq = _to_domain_frequency(body.target_frequency) if body.target_frequency is not None else None
    return habit_out(await service.update_habit(user_id, habit_id, body.name, body.archived, freq))


@router.post("/{habit_id}/logs", response_model=HabitLogOut, status_code=status.HTTP_200_OK)
async def log_habit(
    habit_id: UUID,
    body: HabitLogRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: HabitsService = Depends(get_habits_service),
) -> HabitLogOut:
    """Upsert on (habit, date) -- also how a wrong default gets corrected after the fact."""
    log = await service.log_habit(user_id, habit_id, body.log_date, body.status, body.note)
    return HabitLogOut(
        habit_id=log.habit_id, log_date=log.log_date, status=log.status, note=log.note, is_default=log.is_default,
    )


@router.delete("/{habit_id}/logs/{log_date}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_habit_log(
    habit_id: UUID,
    log_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: HabitsService = Depends(get_habits_service),
) -> Response:
    """Un-log a day. Tomorrow's check-in will propose a default for it again."""
    await service.delete_log(user_id, habit_id, log_date)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
