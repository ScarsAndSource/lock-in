"""
Push actions.

POST /actions/in-app   signed-in. The app runs a notification's action after a deep link (/?a=checkin). iOS web push
                       has no action buttons, so this is the iOS path; Android/desktop use the token route below.
POST /actions/{token}  NO session: the service worker calls it straight from a notification button. Authorised ONLY by
                       the signed, single-use, short-lived token in the push payload (see services/push_actions.py).
                       The user comes from the verified token; the DB transaction gets that user's RLS context, so the
                       action can touch nothing the user couldn't. It is rate limited per client IP.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.cache import data_version
from app.config import Settings, get_settings
from app.dates import Clock
from app.db import AsyncSessionLocal, apply_rls_context
from app.deps import get_action_secret, get_actions_service, get_clock
from app.exceptions import RateLimitedError
from app.netutil import client_ip
from app.ratelimit import get_limiter, rate_limit
from app.schemas_actions import ActionOut, InAppActionRequest, TokenActionRequest
from app.security import get_current_user_id
from app.services import push_actions
from app.services.actions_service import ActionsService
from app.services.companion_wiring import build_stack

router = APIRouter(prefix="/actions", tags=["actions"])

ActionsFactory = Callable[[UUID], AbstractAsyncContextManager[ActionsService]]


def get_actions_factory(settings: Settings = Depends(get_settings), clock: Clock = Depends(get_clock)) -> ActionsFactory:
    """One user-scoped transaction per call. Overridden in tests with in-memory fakes."""

    @asynccontextmanager
    async def factory(user_id: UUID) -> AsyncIterator[ActionsService]:
        async with AsyncSessionLocal() as session:
            async with session.begin():   # claim + effect commit together, or neither does
                if settings.rls_enforced:
                    await apply_rls_context(session, user_id)
                yield build_stack(session, settings, clock).actions
            await data_version.bump(user_id)   # committed: this user's cached evidence is stale

    return factory


@router.post("/in-app", response_model=ActionOut, dependencies=[Depends(rate_limit("api"))])
async def run_in_app(
    body: InAppActionRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ActionsService = Depends(get_actions_service),
) -> ActionOut:
    r = await service.run_in_app(user_id, body.kind, body.action, body.args)
    return ActionOut(status=r.status, message=r.message)


@router.post("/{token}", response_model=ActionOut)
async def run_token(
    token: str,
    body: TokenActionRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
    secret: bytes = Depends(get_action_secret),
    factory: ActionsFactory = Depends(get_actions_factory),
) -> ActionOut:
    if settings.rate_limit_enabled:
        wait = get_limiter().check(
            f"push_action:{client_ip(request, settings.trusted_proxy_hops)}", settings.rate_limit_push_action_per_minute, 60,
        )
        if wait is not None:
            raise RateLimitedError(wait)
    try:
        claims = push_actions.verify(secret, token, clock())
    except push_actions.ActionTokenError as exc:
        # Same body for every failure except expiry, so the endpoint can't be used to probe token structure.
        if exc.code == "expired":
            raise HTTPException(410, "This notification has expired. Open the app.") from exc
        raise HTTPException(401, "Invalid action.") from exc
    async with factory(claims.user_id) as service:
        r = await service.run_token(token, body.action)
    return ActionOut(status=r.status, message=r.message)
