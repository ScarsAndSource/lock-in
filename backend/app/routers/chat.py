from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.deps import get_chat_service
from app.exceptions import RateLimitedError
from app.ratelimit import get_limiter, rate_limit
from app.safety import conversation_has_crisis
from app.schemas_chat import ChatOut, ChatRequest, SupportOut
from app.security import get_current_user_id
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(rate_limit("api"))])


def _enforce_chat_limits(user_id: UUID, settings: Settings) -> None:
    if not settings.rate_limit_enabled:
        return
    for bucket, limit, window in (
        ("chat_min", settings.rate_limit_chat_per_minute, 60),
        ("chat_hour", settings.rate_limit_chat_per_hour, 3600),
    ):
        retry_after = get_limiter().check(f"{bucket}:{user_id}", limit, window)
        if retry_after is not None:
            raise RateLimitedError(retry_after)


@router.post("", response_model=ChatOut)
async def chat(
    body: ChatRequest,
    user_id: UUID = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
    service: ChatService = Depends(get_chat_service),
) -> ChatOut:
    """Stateless: send the last <=6 turns each time. mode: answer | support | no_data | fallback."""
    history = [(t.role, t.content) for t in body.history]
    user_texts = [content for role, content in history if role == "user"]
    if not conversation_has_crisis(body.message, *user_texts):
        _enforce_chat_limits(user_id, settings)  # the support path is never rate-limited
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
