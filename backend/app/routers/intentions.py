from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import get_intentions_service
from app.domain import Intention
from app.ratelimit import rate_limit
from app.schemas_tracking import (
    DueIntentionOut, IntentionCreateRequest, IntentionOut, IntentionPatchRequest,
)
from app.security import get_current_user_id
from app.services.intentions_service import IntentionsService

router = APIRouter(prefix="/intentions", tags=["intentions"], dependencies=[Depends(rate_limit("api"))])
DomainQuery = Literal["habit", "screen_time", "urge", "study", "sleep"]


def _out(i: Intention) -> IntentionOut:
    return IntentionOut(
        id=i.id, linked_domain=i.linked_domain, linked_entity_id=i.linked_entity_id,
        cue=i.cue, action=i.action, active=i.active, created_at=i.created_at,
    )


@router.post("", response_model=IntentionOut, status_code=status.HTTP_201_CREATED)
async def create_intention(
    body: IntentionCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: IntentionsService = Depends(get_intentions_service),
) -> IntentionOut:
    """habit plans need linked_entity_id = your habit; study plans may link a subject; others must not."""
    return _out(await service.create(user_id, body.linked_domain, body.linked_entity_id, body.cue, body.action))


@router.get("", response_model=list[IntentionOut])
async def list_intentions(
    domain: DomainQuery | None = Query(None),
    active_only: bool = Query(False),
    user_id: UUID = Depends(get_current_user_id),
    service: IntentionsService = Depends(get_intentions_service),
) -> list[IntentionOut]:
    return [_out(i) for i in await service.list(user_id, domain, active_only)]


# Static path BEFORE the parameterized ones.
@router.get("/due", response_model=list[DueIntentionOut])
async def due_intentions(
    domain: DomainQuery | None = Query(None, description="Ask with domain=urge when opening urge capture, etc."),
    user_id: UUID = Depends(get_current_user_id),
    service: IntentionsService = Depends(get_intentions_service),
) -> list[DueIntentionOut]:
    return [
        DueIntentionOut(intention=_out(d.intention), level=d.level, reason=d.reason)
        for d in await service.due(user_id, domain)
    ]


@router.patch("/{intention_id}", response_model=IntentionOut)
async def update_intention(
    intention_id: UUID,
    body: IntentionPatchRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: IntentionsService = Depends(get_intentions_service),
) -> IntentionOut:
    return _out(await service.update(user_id, intention_id, body.cue, body.action, body.active))


@router.delete("/{intention_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_intention(
    intention_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: IntentionsService = Depends(get_intentions_service),
) -> Response:
    await service.delete(user_id, intention_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
