from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import get_retro_service
from app.domain import WeeklyRetro
from app.ratelimit import rate_limit
from app.routers.insights import insight_out
from app.schemas_ai import RefreshOut
from app.schemas_retro import RetroCompleteOut, RetroDetailOut, RetroGenerateRequest, RetroOut
from app.security import get_current_user_id
from app.services.retro_service import RetroService

router = APIRouter(prefix="/retros", tags=["retros"], dependencies=[Depends(rate_limit("api"))])


def _retro_out(r: WeeklyRetro) -> RetroOut:
    return RetroOut(
        id=r.id, week_start=r.week_start, week_end=r.week_end, generated_at=r.generated_at,
        narrative=r.narrative, next_step=r.next_step, summary=r.summary,
        evidence_refs=r.evidence_refs, narrated=r.narrated, completed_at=r.completed_at,
    )


async def _detail(service: RetroService, user_id: UUID, r: WeeklyRetro) -> RetroDetailOut:
    pending = await service.pending_ratings(user_id, r.week_end)
    return RetroDetailOut(
        **_retro_out(r).model_dump(),
        status="completed" if r.completed_at else "ready",
        pending_ratings=[insight_out(i) for i in pending],
    )


@router.get("", response_model=list[RetroOut])
async def list_retros(
    limit: int = Query(12, ge=1, le=52),
    user_id: UUID = Depends(get_current_user_id),
    service: RetroService = Depends(get_retro_service),
) -> list[RetroOut]:
    return [_retro_out(r) for r in await service.list(user_id, limit)]


# Static paths BEFORE the parameterized "/{week_start}".
@router.get("/latest", response_model=RetroDetailOut)
async def latest_retro(
    user_id: UUID = Depends(get_current_user_id),
    service: RetroService = Depends(get_retro_service),
) -> RetroDetailOut:
    return await _detail(service, user_id, await service.get(user_id, None))


@router.post(
    "/generate", response_model=RetroDetailOut, status_code=status.HTTP_201_CREATED,
)
async def generate_retro(
    response: Response,
    body: RetroGenerateRequest | None = None,
    user_id: UUID = Depends(get_current_user_id),
    service: RetroService = Depends(get_retro_service),
) -> RetroDetailOut:
    """Idempotent. 201 = generated now, 200 = that week's retro already existed. Completed weeks only."""
    retro, created = await service.generate(user_id, body.week_start if body else None)
    if not created:
        response.status_code = status.HTTP_200_OK
    return await _detail(service, user_id, retro)


@router.get("/{week_start}", response_model=RetroDetailOut)
async def get_retro(
    week_start: date,
    user_id: UUID = Depends(get_current_user_id),
    service: RetroService = Depends(get_retro_service),
) -> RetroDetailOut:
    return await _detail(service, user_id, await service.get(user_id, week_start))


@router.post("/{week_start}/complete", response_model=RetroCompleteOut)
async def complete_retro(
    week_start: date,
    user_id: UUID = Depends(get_current_user_id),
    service: RetroService = Depends(get_retro_service),
) -> RetroCompleteOut:
    """Marks retro done and attempts insight refresh. If too many insights unrated → rate_previous_first."""
    retro, refresh = await service.complete(user_id, week_start)
    return RetroCompleteOut(
        retro=_retro_out(retro),
        insights=RefreshOut(generated=[insight_out(i) for i in refresh.created], skipped_reason=refresh.skipped_reason),
    )
