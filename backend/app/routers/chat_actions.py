from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.deps import get_agent_chat_service
from app.ratelimit import rate_limit
from app.schemas_chat import ActionCardOut, ConfirmActionRequest, UndoActionRequest, UndoOut
from app.security import get_current_user_id
from app.services.chat_agent import AgentChatService

router = APIRouter(prefix="/chat/actions", tags=["chat-actions"], dependencies=[Depends(rate_limit("api"))])


@router.post("/confirm", response_model=ActionCardOut)
async def confirm_action(
    body: ConfirmActionRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: AgentChatService = Depends(get_agent_chat_service),
) -> ActionCardOut:
    """Apply a PENDING card. The client sends back only the signed, single-use token it was given; what to do comes from
    the token, and is re-validated server side exactly like model output. No model call, so no AI allowance is used."""
    c = await service.confirm(user_id, body.token)
    return ActionCardOut(
        id=c.id, tool=c.tool, status=c.status, summary=c.summary, reason=c.reason, undo_token=c.undo_token,
    )


@router.post("/undo", response_model=UndoOut)
async def undo_action(
    body: UndoActionRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: AgentChatService = Depends(get_agent_chat_service),
) -> UndoOut:
    """The 'Logged. Undo' chip. Restores exactly what the action replaced (or removes what it created)."""
    return UndoOut(message=await service.undo(user_id, body.token))
