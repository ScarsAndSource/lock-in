from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.config import Settings, get_settings
from app.deps import get_chat_threads_service
from app.ratelimit import rate_limit
from app.routers.chat import _enforce_chat_limits
from app.schemas_chat import SupportOut
from app.schemas_threads import (
    DeletedOut, MessageOut, RenameThreadRequest, SendMessageOut, SendMessageRequest,
    ThreadDetailOut, ThreadOut,
)
from app.security import get_current_user_id
from app.services.chat_threads_service import ChatThreadsService, MessageView, ThreadView

router = APIRouter(prefix="/chat", tags=["chat-threads"], dependencies=[Depends(rate_limit("api"))])


def _thread_out(v: ThreadView) -> ThreadOut:
    t = v.thread
    return ThreadOut(
        id=t.id,
        title=v.title,
        created_at=t.created_at,
        last_message_at=t.last_message_at,
        message_count=v.message_count,
    )


def _message_out(v: MessageView) -> MessageOut:
    m = v.message
    return MessageOut(
        id=m.id,
        role=m.role,
        content=v.content,
        next_step=v.next_step,
        mode=v.mode,
        cited_days=v.cited_days,
        narrated=v.narrated,
        model=v.model,
        created_at=m.created_at,
    )


@router.post("/messages", response_model=SendMessageOut)
async def send_message(
    body: SendMessageRequest,
    user_id: UUID = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
    service: ChatThreadsService = Depends(get_chat_threads_service),
) -> SendMessageOut:
    """Omit thread_id to start a conversation. Stored encrypted; the server loads the history itself.
    Chat rate limits apply only when the model is actually called -- never to the crisis/support path."""
    r = await service.send(
        user_id, body.message, body.thread_id,
        before_model=lambda: _enforce_chat_limits(user_id, settings)
    )
    return SendMessageOut(
        thread=_thread_out(r.thread),
        user_message=_message_out(r.user_message),
        reply=_message_out(r.reply),
        support=SupportOut.model_validate(r.support) if r.support else None,
    )


@router.get("/threads", response_model=list[ThreadOut])
async def list_threads(
    limit: int = Query(50, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),
    service: ChatThreadsService = Depends(get_chat_threads_service),
) -> list[ThreadOut]:
    return [_thread_out(v) for v in await service.list_threads(user_id, limit)]


@router.get("/threads/{thread_id}", response_model=ThreadDetailOut)
async def get_thread(
    thread_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    before: datetime | None = Query(None, description="Cursor: the created_at of the oldest message you already have."),
    user_id: UUID = Depends(get_current_user_id),
    service: ChatThreadsService = Depends(get_chat_threads_service),
) -> ThreadDetailOut:
    d = await service.get_thread(user_id, thread_id, limit, before)
    return ThreadDetailOut(
        thread=_thread_out(d.thread),
        messages=[_message_out(m) for m in d.messages],
        has_more=d.has_more,
        support=SupportOut.model_validate(d.support) if d.support else None,
    )


@router.patch("/threads/{thread_id}", response_model=ThreadOut)
async def rename_thread(
    thread_id: UUID,
    body: RenameThreadRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ChatThreadsService = Depends(get_chat_threads_service),
) -> ThreadOut:
    return _thread_out(await service.rename(user_id, thread_id, body.title))


# Static path BEFORE the parameterized delete is irrelevant here (different path shapes), but kept explicit.
@router.delete("/threads", response_model=DeletedOut)
async def delete_all_threads(
    user_id: UUID = Depends(get_current_user_id),
    service: ChatThreadsService = Depends(get_chat_threads_service),
) -> DeletedOut:
    """Wipe every stored conversation."""
    return DeletedOut(deleted=await service.delete_all(user_id))


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_thread(
    thread_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ChatThreadsService = Depends(get_chat_threads_service),
) -> Response:
    await service.delete(user_id, thread_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
