from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import get_companion_service
from app.ratelimit import rate_limit
from app.schemas_companion import CompanionNowOut, EventIn, NextActionOut, RhythmOut
from app.security import get_current_user_id
from app.services.companion_service import CompanionService

router = APIRouter(prefix="/companion", tags=["companion"], dependencies=[Depends(rate_limit("api"))])


@router.get("/now", response_model=CompanionNowOut)
async def get_now(
    skip: list[str] = Query(default=[]),
    user_id: UUID = Depends(get_current_user_id),
    service: CompanionService = Depends(get_companion_service),
) -> CompanionNowOut:
    """The one thing to do now, plus the shape of the person's day. `skip` = keys the person said "not now" to."""
    data = await service.now(user_id, skip)
    return CompanionNowOut(
        next_action=NextActionOut(**asdict(data.action)),
        rhythm=RhythmOut(**asdict(data.rhythm)),
        local_minute=data.local_minute,
        tone=data.tone,  # type: ignore[arg-type]  -- resolve_tone only returns 'direct' | 'coach'
        habits_done=data.habits_done,
        habits_total=data.habits_total,
        confirmed=data.confirmed,
    )


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def post_event(
    body: EventIn,
    user_id: UUID = Depends(get_current_user_id),
    service: CompanionService = Depends(get_companion_service),
) -> Response:
    """Fire-and-forget usage signal (an app open, what the companion showed, what the person did with it)."""
    await service.record_event(user_id, body.kind, body.ref)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
