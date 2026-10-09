from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import get_urges_service
from app.ratelimit import rate_limit
from app.schemas_tracking import UrgeCaptureRequest, UrgeDetailRequest, UrgeOut, UrgeSummaryOut
from app.security import get_current_user_id
from app.services.urges_service import UrgesService, UrgeView

router = APIRouter(prefix="/urges", tags=["urges"], dependencies=[Depends(rate_limit("api"))])


def _out(v: UrgeView) -> UrgeOut:
    l = v.log
    return UrgeOut(
        id=l.id, occurred_at=l.occurred_at, log_date=l.log_date, outcome=l.outcome, intensity=l.intensity,
        has_detail=l.has_detail, trigger_context=v.trigger_context, coping_strategy=v.coping_strategy, note=v.note,
    )


@router.post("", response_model=UrgeOut, status_code=status.HTTP_201_CREATED)
async def capture_urge(
    body: UrgeCaptureRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: UrgesService = Depends(get_urges_service),
) -> UrgeOut:
    """The 2-tap path: {"outcome": "resisted"} or {"outcome": "relapsed"} is a complete log."""
    return _out(await service.capture(
        user_id, body.outcome, body.occurred_at, body.intensity,
        body.trigger_context, body.coping_strategy, body.note,
    ))


@router.patch("/{urge_id}", response_model=UrgeOut)
async def add_urge_detail(
    urge_id: UUID,
    body: UrgeDetailRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: UrgesService = Depends(get_urges_service),
) -> UrgeOut:
    """Add-later detail. Only the fields you send change; null or "" clears one."""
    return _out(await service.add_detail(user_id, urge_id, body.model_dump(exclude_unset=True)))


@router.get("", response_model=list[UrgeOut])
async def list_urges(
    start_date: date = Query(...),
    end_date: date = Query(...),
    details: bool = Query(False, description="Include decrypted trigger/coping/note text."),
    user_id: UUID = Depends(get_current_user_id),
    service: UrgesService = Depends(get_urges_service),
) -> list[UrgeOut]:
    return [_out(v) for v in await service.list_views(user_id, start_date, end_date, details)]


@router.get("/summary", response_model=UrgeSummaryOut)
async def urge_summary(
    days: int = Query(7, ge=7, le=90),
    user_id: UUID = Depends(get_current_user_id),
    service: UrgesService = Depends(get_urges_service),
) -> UrgeSummaryOut:
    end, s, prev_rate = await service.summary(user_id, None, days)
    return UrgeSummaryOut(
        end_date=end, window_days=days, total=s.total, resisted=s.resisted, relapsed=s.relapsed,
        resist_rate_pct=s.resist_rate_pct, relapse_free_days_pct=s.relapse_free_days_pct,
        prev_resist_rate_pct=prev_rate,
    )


@router.delete("/{urge_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_urge(
    urge_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: UrgesService = Depends(get_urges_service),
) -> Response:
    await service.delete(user_id, urge_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
