"""
Passive capture endpoints.

POST   /ingest/tokens        signed-in: create a per-device token (returned ONCE). Optional habit_id makes it a
                             habit-bound key that can only mark that one habit done.
GET    /ingest/tokens        signed-in: list automations (never the token strings)
DELETE /ingest/tokens/{id}   signed-in: revoke one automation, effective immediately
POST   /ingest/event         NO session: an OS automation (iOS Shortcut, Tasker, MacroDroid) sends
                             Authorization: Bearer <token> and {"kind": "sleep_start" | "sleep_end" | "screen_time" |
                             "habit_done", ...}. Write-only: it can add these events and nothing else. Rate limited per token.
GET|POST /ingest/u/{token}/{kind}
                             The same thing with the token INSIDE the URL, for automation apps where headers and JSON
                             bodies are the hard part: one pasted URL per automation. GET is accepted on purpose (it is the
                             default method of nearly every automation app) and is safe to repeat: every kind is an
                             idempotent upsert. Optional query: minutes and date (screen_time), at (ISO time with offset).
                             A token in a URL can end up in logs, so main.py redacts it from the access log; the token is
                             still write-only, per-device and revocable, so a leaked URL can do no more than add a sleep or
                             habit-done entry until it is revoked.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from app.config import Settings, get_settings
from app.dates import Clock
from app.db import AsyncSessionLocal, apply_rls_context
from app.deps import get_action_secret, get_clock, get_ingest_service
from app.exceptions import RateLimitedError
from app.ratelimit import get_limiter, rate_limit
from app.schemas_ingest import (
    IngestEvent, IngestKind, IngestOut, IngestTokenCreate, IngestTokenCreated, IngestTokenOut,
)
from app.security import get_current_user_id
from app.services.companion_wiring import build_stack
from app.services.ingest_service import IngestAuthError, IngestService, purpose_secret, verify_token

router = APIRouter(prefix="/ingest", tags=["ingest"])
IngestFactory = Callable[[UUID], AbstractAsyncContextManager[IngestService]]
_manage = [Depends(rate_limit("api"))]


def get_ingest_factory(settings: Settings = Depends(get_settings), clock: Clock = Depends(get_clock)) -> IngestFactory:
    """One user-scoped transaction per event (RLS context from the verified token). Overridden in tests."""

    @asynccontextmanager
    async def factory(user_id: UUID) -> AsyncIterator[IngestService]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                if settings.rls_enforced:
                    await apply_rls_context(session, user_id)
                yield build_stack(session, settings, clock).ingest

    return factory


def _out(t) -> IngestTokenOut:
    return IngestTokenOut(
        id=t.id, label=t.label, created_at=t.created_at, last_used_at=t.last_used_at, revoked_at=t.revoked_at,
        habit_id=t.habit_id,
    )


@router.post("/tokens", response_model=IngestTokenCreated, status_code=201, dependencies=_manage)
async def create_token(
    body: IngestTokenCreate, user_id: UUID = Depends(get_current_user_id),
    service: IngestService = Depends(get_ingest_service),
) -> IngestTokenCreated:
    row, token = await service.create_token(user_id, body.label, body.habit_id)
    return IngestTokenCreated(**_out(row).model_dump(), token=token)


@router.get("/tokens", response_model=list[IngestTokenOut], dependencies=_manage)
async def list_tokens(
    user_id: UUID = Depends(get_current_user_id), service: IngestService = Depends(get_ingest_service),
) -> list[IngestTokenOut]:
    return [_out(t) for t in await service.list_tokens(user_id)]


@router.delete("/tokens/{token_id}", status_code=204, response_class=Response, dependencies=_manage)
async def revoke_token(
    token_id: UUID, user_id: UUID = Depends(get_current_user_id), service: IngestService = Depends(get_ingest_service),
) -> Response:
    await service.revoke(user_id, token_id)
    return Response(status_code=204)


async def _run_event(
    token: str, kind: str, at: datetime | None, minutes: int | None, day: date | None,
    settings: Settings, base_secret: bytes, factory: IngestFactory,
) -> IngestOut:
    """Shared by the header route and the URL route, so both get exactly the same auth, rate limit and rules."""
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked token.", headers={"WWW-Authenticate": "Bearer"})
    try:
        user_id, token_id = verify_token(purpose_secret(base_secret), token.strip())
    except IngestAuthError:
        raise unauthorized from None
    if settings.rate_limit_enabled:
        wait = get_limiter().check(f"ingest:{token_id}", settings.rate_limit_ingest_per_minute, 60)
        if wait is not None:
            raise RateLimitedError(wait)
    try:
        async with factory(user_id) as service:
            r = await service.handle_event(user_id, token_id, kind, at, minutes, day)
    except IngestAuthError:
        raise unauthorized from None        # unknown / revoked: same answer as a forged token
    return IngestOut(kind=r.kind, date=r.day, message=r.message)


@router.post("/event", response_model=IngestOut)
async def ingest_event(
    body: IngestEvent,
    authorization: str | None = Header(None),
    settings: Settings = Depends(get_settings),
    base_secret: bytes = Depends(get_action_secret),
    factory: IngestFactory = Depends(get_ingest_factory),
) -> IngestOut:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked token.", headers={"WWW-Authenticate": "Bearer"})
    return await _run_event(token, body.kind, body.at, body.minutes, body.date, settings, base_secret, factory)


@router.api_route("/u/{token}/{kind}", methods=["GET", "POST"], response_model=IngestOut)
async def ingest_event_by_url(
    token: str,
    kind: IngestKind,
    at: datetime | None = Query(default=None),
    minutes: int | None = Query(default=None, ge=0, le=1440),
    day: date | None = Query(default=None, alias="date"),
    settings: Settings = Depends(get_settings),
    base_secret: bytes = Depends(get_action_secret),
    factory: IngestFactory = Depends(get_ingest_factory),
) -> IngestOut:
    return await _run_event(token, kind, at, minutes, day, settings, base_secret, factory)
