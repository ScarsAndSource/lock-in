"""
Insights router stub for slice 8.
Exposes insight_out() as a public helper so routers/retros.py can import it.
Full insights endpoints are wired in the insights slice.
"""
from __future__ import annotations

from app.domain import PatternInsight
from app.schemas_ai import InsightOut

from fastapi import APIRouter

router = APIRouter(prefix="/insights", tags=["insights"])


def _out(i: PatternInsight) -> InsightOut:
    return InsightOut(
        id=i.id, generated_on=i.generated_on, generated_at=i.generated_at,
        pattern_key=i.pattern_key, insight_text=i.insight_text, next_step=i.next_step,
        source_domains=i.source_domains, narrated=i.narrated, user_feedback=i.user_feedback,
    )


insight_out = _out  # shared with the retro router
