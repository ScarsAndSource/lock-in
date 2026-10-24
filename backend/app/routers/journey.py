from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.deps import get_journey_service
from app.ratelimit import rate_limit
from app.schemas_journey import (
    CheckRequest, FocusRequest, RecallCreateRequest, RecallDoneRequest, SeasonStartRequest, SnapshotRequest,
)
from app.security import get_current_user_id
from app.services.journey_service import JourneyService

router = APIRouter(prefix="/journey", tags=["journey"], dependencies=[Depends(rate_limit("api"))])


def _no_content() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- state, seasons
@router.get("/state")
async def state(user_id: UUID = Depends(get_current_user_id), svc: JourneyService = Depends(get_journey_service)) -> dict:
    return await svc.state(user_id)


@router.post("/season", status_code=status.HTTP_201_CREATED)
async def start_season(
    body: SeasonStartRequest, user_id: UUID = Depends(get_current_user_id),
    svc: JourneyService = Depends(get_journey_service),
) -> dict:
    return await svc.start_season(user_id, body.name, body.focus_habit_ids)


@router.put("/season/focus")
async def set_focus(
    body: FocusRequest, user_id: UUID = Depends(get_current_user_id),
    svc: JourneyService = Depends(get_journey_service),
) -> dict:
    return await svc.set_focus(user_id, body.focus_habit_ids)


@router.get("/nudge")
async def nudge(user_id: UUID = Depends(get_current_user_id), svc: JourneyService = Depends(get_journey_service)) -> dict | None:
    return await svc.nudge(user_id)


# ---- exam radar
@router.get("/recall")
async def list_recall(
    user_id: UUID = Depends(get_current_user_id), svc: JourneyService = Depends(get_journey_service),
) -> list[dict]:
    return await svc.list_recall(user_id)


@router.post("/recall", status_code=status.HTTP_201_CREATED)
async def create_recall(
    body: RecallCreateRequest, user_id: UUID = Depends(get_current_user_id),
    svc: JourneyService = Depends(get_journey_service),
) -> list[dict]:
    return await svc.create_recall(user_id, body.label, body.topics, body.exam_date)


@router.get("/recall/due")
async def due_recall(
    user_id: UUID = Depends(get_current_user_id), svc: JourneyService = Depends(get_journey_service),
) -> list[dict]:
    return await svc.due_recall(user_id)


@router.post("/recall/review/{review_id}/done", status_code=status.HTTP_204_NO_CONTENT)
async def review_done(
    review_id: UUID, body: RecallDoneRequest, user_id: UUID = Depends(get_current_user_id),
    svc: JourneyService = Depends(get_journey_service),
) -> Response:
    await svc.mark_review_done(user_id, review_id, body.extra_topics)
    return _no_content()


@router.delete("/recall/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_recall(
    set_id: UUID, user_id: UUID = Depends(get_current_user_id), svc: JourneyService = Depends(get_journey_service),
) -> Response:
    await svc.archive_recall(user_id, set_id)
    return _no_content()


# ---- life snapshot
@router.get("/snapshot")
async def snapshot(user_id: UUID = Depends(get_current_user_id), svc: JourneyService = Depends(get_journey_service)) -> dict:
    return await svc.snapshot_view(user_id)


@router.post("/snapshot", status_code=status.HTTP_201_CREATED)
async def submit_snapshot(
    body: SnapshotRequest, user_id: UUID = Depends(get_current_user_id),
    svc: JourneyService = Depends(get_journey_service),
) -> dict:
    return await svc.submit_snapshot(user_id, body)


# ---- graduation shelf
@router.get("/shelf")
async def shelf(user_id: UUID = Depends(get_current_user_id), svc: JourneyService = Depends(get_journey_service)) -> dict:
    return await svc.shelf(user_id)


@router.post("/graduate/{habit_id}", status_code=status.HTTP_201_CREATED)
async def graduate(
    habit_id: UUID, user_id: UUID = Depends(get_current_user_id), svc: JourneyService = Depends(get_journey_service),
) -> dict:
    return await svc.graduate(user_id, habit_id)


@router.post("/shelf/{grad_id}/check")
async def shelf_check(
    grad_id: UUID, body: CheckRequest, user_id: UUID = Depends(get_current_user_id),
    svc: JourneyService = Depends(get_journey_service),
) -> dict:
    return await svc.shelf_check(user_id, grad_id, body.holding)


@router.post("/shelf/{grad_id}/revive")
async def revive(
    grad_id: UUID, user_id: UUID = Depends(get_current_user_id), svc: JourneyService = Depends(get_journey_service),
) -> dict:
    return await svc.revive(user_id, grad_id)