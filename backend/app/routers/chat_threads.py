from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.config import Settings, get_settings
from app.deps import get_chat_threads_service
from app.limits.idempotency import Idempotency
from app.limits.turn import turn_scope
from app.ratelimit import rate_limit
from app.schemas_chat import ActionCardOut, SupportOut
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
        actions=[ActionCardOut(
            id=c.id, tool=c.tool, status=c.status, summary=c.summary, reason=c.reason, args=c.args, undo=c.undo,
        ) for c in v.actions],
        created_at=m.created_at,
    )


def _fingerprint(body: SendMessageRequest) -> str:
    """What makes two requests 'the same message' for Idempotency-Key purposes."""
    raw = f"{body.thread_id or ''}\x00{body.message}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@router.post("/messages", response_model=SendMessageOut)
async def send_message(
    body: SendMessageRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
    service: ChatThreadsService = Depends(get_chat_threads_service),
) -> SendMessageOut:
    """Omit thread_id to start a conversation. Stored encrypted; the server loads the history itself.

    Idempotency-Key (optional): a repeat of the same request returns the SAME reply without another model call or
    another stored message. The turn (per-user lock + one rate slot) is charged only when the model is actually
    called -- never on the crisis/support path."""
    idem = Idempotency(user_id, idempotency_key, _fingerprint(body), settings)
    replay = await idem.begin()
    if replay is not None:
        return SendMessageOut.model_validate_json(replay)

    try:
        async with turn_scope(user_id, settings):
            r = await service.send(user_id, body.message, body.thread_id)
        out = SendMessageOut(
            thread=_thread_out(r.thread),
            user_message=_message_out(r.user_message),
            reply=_message_out(r.reply),
            support=SupportOut.model_validate(r.support) if r.support else None,
        )
    except BaseException:
        await idem.abort()   # a refused or failed attempt must not block the client's retry
        raise
    await idem.complete(out.model_dump_json())
    return out


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
