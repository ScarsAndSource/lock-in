from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.deps import get_goals_service
from app.domain import Goal, GoalStatus
from app.ratelimit import rate_limit
from app.schemas_tracking import GoalCreateRequest, GoalOut, GoalPatchRequest, GoalProgressOut
from app.security import get_current_user_id
from app.services.goals_service import GoalsService

router = APIRouter(prefix="/goals", tags=["goals"], dependencies=[Depends(rate_limit("api"))])


def goal_out(g: Goal) -> GoalOut:
    return GoalOut(
        id=g.id, domain=g.domain, definition=g.definition, target=g.target, status=g.status, created_at=g.created_at,
    )


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
async def create_goal(
    body: GoalCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: GoalsService = Depends(get_goals_service),
) -> GoalOut:
    """target by domain: habit {habit_id, min_consistency_pct?, window_days?} | screen_time
    {max_minutes_per_day, min_days_within_pct?, window_days?} | sleep {min_minutes_per_night, min_nights_pct?,
    window_days?, bedtime?, wake?} | study {weekly_minutes} | urge {min_relapse_free_days_pct?, window_days?}"""
    return goal_out(await service.create(user_id, body.domain, body.definition, body.target))


@router.get("", response_model=list[GoalOut])
async def list_goals(
    status_filter: GoalStatus | None = Query(None, alias="status"),
    user_id: UUID = Depends(get_current_user_id),
    service: GoalsService = Depends(get_goals_service),
) -> list[GoalOut]:
    return [goal_out(g) for g in await service.list(user_id, status_filter)]


@router.get("/progress", response_model=list[GoalProgressOut])
async def goal_progress(
    user_id: UUID = Depends(get_current_user_id),
    service: GoalsService = Depends(get_goals_service),
) -> list[GoalProgressOut]:
    return [
        GoalProgressOut(
            goal=goal_out(p.goal), current=p.current, target_value=p.target_value, unit=p.unit,
            on_track=p.on_track, detail=p.detail,
        )
        for p in await service.progress(user_id)
    ]


@router.patch("/{goal_id}", response_model=GoalOut)
async def update_goal(
    goal_id: UUID,
    body: GoalPatchRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: GoalsService = Depends(get_goals_service),
) -> GoalOut:
    """Pause / achieve / archive with status; there's no delete, history stays."""
    return goal_out(await service.update(user_id, goal_id, body.definition, body.status, body.target))
