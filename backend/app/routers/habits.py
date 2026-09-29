from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_habits_service
from app.domain import TargetFrequency
from app.exceptions import NotFoundError
from app.schemas import HabitCreateRequest, HabitLogOut, HabitLogRequest, HabitOut
from app.security import get_current_user_id
from app.services.habits_service import HabitsService

router = APIRouter(prefix="/habits", tags=["habits"])


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
    return HabitOut(
        id=habit.id,
        name=habit.name,
        target_frequency=body.target_frequency.model_dump(),
        archived_at=habit.archived_at,
    )


@router.get("", response_model=list[HabitOut])
async def list_habits(
    user_id: UUID = Depends(get_current_user_id),
    service: HabitsService = Depends(get_habits_service),
) -> list[HabitOut]:
    habits = await service.list_habits(user_id)
    return [
        HabitOut(
            id=h.id,
            name=h.name,
            target_frequency=(
                {"type": "weekdays", "days": list(h.target_frequency.days)}
                if h.target_frequency.type == "weekdays"
                else {"type": "n_per_week", "count": h.target_frequency.count}
            ),
            archived_at=h.archived_at,
        )
        for h in habits
    ]


@router.post("/{habit_id}/logs", response_model=HabitLogOut, status_code=status.HTTP_200_OK)
async def log_habit(
    habit_id: UUID,
    body: HabitLogRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: HabitsService = Depends(get_habits_service),
) -> HabitLogOut:
    """
    Logs (or corrects, since this is an upsert keyed on habit_id+log_date) a
    habit's status for any date, not just today — this is the mechanism
    behind SPEC.md section 8's "a default gets it wrong" edge case: fixing
    a wrongly-applied default after the fact is the same call as logging it
    the first time.
    """
    try:
        log = await service.log_habit(user_id, habit_id, body.log_date, body.status, body.note)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return HabitLogOut(
        habit_id=log.habit_id, log_date=log.log_date, status=log.status,
        note=log.note, is_default=log.is_default,
    )
