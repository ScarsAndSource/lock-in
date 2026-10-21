"""GET /companion/inference?day=YYYY-MM-DD -> one yes/no question about last night, or null."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_clock, get_db, get_profile_service
from app.dates import Clock
from app.ratelimit import rate_limit
from app.repositories.companion_repository import SqlAlchemyCompanionRepository
from app.repositories.send_time_repository import SqlAlchemySendTimeRepository
from app.repositories.sleep_repository import SqlAlchemySleepRepository
from app.schemas_inference import InferenceOut
from app.security import get_current_user_id
from app.services.inference import InferenceService, hhmm
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/companion", tags=["companion"], dependencies=[Depends(rate_limit("api"))])


def get_inference_service(
    session: AsyncSession = Depends(get_db),
    profiles: ProfileService = Depends(get_profile_service),
    clock: Clock = Depends(get_clock),
) -> InferenceService:
    return InferenceService(
        SqlAlchemySleepRepository(session), SqlAlchemySendTimeRepository(session),
        SqlAlchemyCompanionRepository(session), profiles, clock,
    )


@router.get("/inference", response_model=InferenceOut | None)
async def get_inference(
    day: date = Query(..., description="The wake date of the night in question"),
    user_id: UUID = Depends(get_current_user_id),
    service: InferenceService = Depends(get_inference_service),
) -> InferenceOut | None:
    found = await service.infer_sleep(user_id, day)
    if found is None:
        return None
    return InferenceOut(
        day=found.day, kind="sleep", time_to_bed=hhmm(found.bed), time_woke=hhmm(found.wake),
        duration_minutes=found.duration_minutes, confidence=found.confidence,  # type: ignore[arg-type]
        basis=list(found.basis), prompt=found.prompt,
    )
