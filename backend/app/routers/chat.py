from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.deps import get_chat_service
from app.limits.turn import turn_scope
from app.ratelimit import rate_limit
from app.schemas_chat import ChatOut, ChatRequest, SupportOut
from app.security import get_current_user_id
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(rate_limit("api"))])


@router.post("", response_model=ChatOut)
async def chat(
    body: ChatRequest,
    user_id: UUID = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
    service: ChatService = Depends(get_chat_service),
) -> ChatOut:
    """Stateless: send the last <=6 turns each time. mode: answer | support | no_data | fallback.
    The turn is charged (lock + rate slot) only when the model is actually called, so the crisis/support path and
    the no-data reply are never limited."""
    history = [(t.role, t.content) for t in body.history]
    async with turn_scope(user_id, settings):
        r = await service.reply(user_id, body.message, history)
    return ChatOut(
        mode=r.mode,
        reply=r.reply,
        next_step=r.next_step,
        cited_days=r.cited_days,
        narrated=r.narrated,
        model=r.model,
        support=SupportOut.model_validate(r.support) if r.support else None,
    )
