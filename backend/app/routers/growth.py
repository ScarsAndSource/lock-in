from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import get_growth_service, get_profile_service
from app.ratelimit import rate_limit
from app.safety import is_crisis, support_payload
from app.schemas_growth import (
    AutopsyApplyRequest, FutureCreateRequest, FutureOut, FuturePatchRequest, IdentityOut, IdentityPutRequest,
    JournalEntryOut, JournalPutOut, JournalPutRequest, MessageOut, PromptOut,
)
from app.security import get_current_user_id
from app.services.growth_service import GrowthService
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/growth", tags=["growth"], dependencies=[Depends(rate_limit("api"))])


def _no_content() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- the one gentle prompt slot on Now
@router.get("/prompt", response_model=PromptOut)
async def prompt(
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> dict:
    return await service.prompt(user_id)


# ---- identity
@router.get("/identity", response_model=IdentityOut | None)
async def get_identity(
    week_start: date | None = Query(None, description="Count votes for that Monday-Sunday week; default last 7 days."),
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> dict | None:
    return await service.get_identity(user_id, week_start)


@router.put("/identity", response_model=IdentityOut)
async def put_identity(
    body: IdentityPutRequest,
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> dict:
    return await service.put_identity(
        user_id, body.matters, body.why_now, body.importance, body.confidence, body.sentence,
    )


@router.delete("/identity", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_identity(
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> Response:
    await service.delete_identity(user_id)
    return _no_content()


# ---- little notes (journal)
@router.get("/journal", response_model=list[JournalEntryOut])
async def list_journal(
    days: int = Query(14, ge=1, le=60),
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> list[dict]:
    return await service.list_journal(user_id, days)


@router.put("/journal/{entry_date}", response_model=JournalPutOut)
async def put_journal(
    entry_date: date, body: JournalPutRequest,
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
    profiles: ProfileService = Depends(get_profile_service),
) -> dict:
    entry = await service.put_journal(user_id, entry_date, body.text, body.sticker)
    support = None
    if body.text and is_crisis(body.text):   # the save already went through, same as the check-in note
        support = support_payload((await profiles.get(user_id)).timezone)
    return {"entry": entry, "support": support}


# ---- habit check-up
@router.post("/autopsy/{autopsy_id}/apply", response_model=MessageOut)
async def apply_autopsy(
    autopsy_id: UUID, body: AutopsyApplyRequest,
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> dict:
    return await service.apply_autopsy(user_id, autopsy_id, body.reason, body.floor_text, body.cue, body.choice)


@router.post("/autopsy/{autopsy_id}/later", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def autopsy_later(
    autopsy_id: UUID,
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> Response:
    await service.defer_autopsy(user_id, autopsy_id, skip=False)
    return _no_content()


@router.post("/autopsy/{autopsy_id}/skip", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def autopsy_skip(
    autopsy_id: UUID,
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> Response:
    await service.defer_autopsy(user_id, autopsy_id, skip=True)
    return _no_content()


# ---- notes to future self
@router.get("/future", response_model=list[FutureOut])
async def list_future(
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> list[dict]:
    return await service.list_future(user_id)


@router.post("/future", response_model=FutureOut, status_code=status.HTTP_201_CREATED)
async def create_future(
    body: FutureCreateRequest,
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> dict:
    return await service.create_future(
        user_id, body.text, body.audio_b64, body.audio_mime, body.duration_s, body.send_at,
    )


@router.get("/future/{message_id}", response_model=FutureOut)
async def get_future(
    message_id: UUID,
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> dict:
    return await service.get_future(user_id, message_id)


@router.post("/future/{message_id}/played", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def future_played(
    message_id: UUID,
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> Response:
    await service.mark_future_played(user_id, message_id)
    return _no_content()


@router.patch("/future/{message_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def patch_future(
    message_id: UUID, body: FuturePatchRequest,
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> Response:
    await service.set_future_active(user_id, message_id, body.active)
    return _no_content()


@router.delete("/future/{message_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_future(
    message_id: UUID,
    user_id: UUID = Depends(get_current_user_id), service: GrowthService = Depends(get_growth_service),
) -> Response:
    await service.delete_future(user_id, message_id)
    return _no_content()
