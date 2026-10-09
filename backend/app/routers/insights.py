from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.deps import get_insights_service
from app.domain import PatternInsight
from app.ratelimit import rate_limit
from app.schemas_ai import InsightFeedbackRequest, InsightOut, RefreshOut
from app.security import get_current_user_id
from app.services.insights_service import InsightsService

router = APIRouter(prefix="/insights", tags=["insights"], dependencies=[Depends(rate_limit("api"))])
_refresh_limit = rate_limit(
    "insights_refresh", limit_setting="rate_limit_insights_refresh_per_hour", window_seconds=3600
)


def _out(i: PatternInsight) -> InsightOut:
    return InsightOut(
        id=i.id, generated_on=i.generated_on, generated_at=i.generated_at,
        pattern_key=i.pattern_key, insight_text=i.insight_text, next_step=i.next_step,
        source_domains=i.source_domains, narrated=i.narrated, user_feedback=i.user_feedback,
    )


insight_out = _out  # shared with the retro router


@router.get("", response_model=list[InsightOut])
async def list_insights(
    limit: int = Query(20, ge=1, le=100),
    unrated_only: bool = Query(False),
    user_id: UUID = Depends(get_current_user_id),
    service: InsightsService = Depends(get_insights_service),
) -> list[InsightOut]:
    return [_out(i) for i in await service.list(user_id, limit, unrated_only)]


@router.post("/refresh", response_model=RefreshOut, dependencies=[Depends(_refresh_limit)])
async def refresh_insights(
    user_id: UUID = Depends(get_current_user_id),
    service: InsightsService = Depends(get_insights_service),
) -> RefreshOut:
    """skipped_reason: rate_previous_first | no_patterns | no_new_patterns | null."""
    result = await service.refresh(user_id)
    return RefreshOut(generated=[_out(i) for i in result.created], skipped_reason=result.skipped_reason)


@router.post("/{insight_id}/feedback", response_model=InsightOut)
async def rate_insight(
    insight_id: UUID,
    body: InsightFeedbackRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: InsightsService = Depends(get_insights_service),
) -> InsightOut:
    return _out(await service.set_feedback(user_id, insight_id, body.feedback))
