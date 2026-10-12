from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status

from app.config import Settings, get_settings
from app.deps import get_notifications_service
from app.ratelimit import rate_limit
from app.schemas_tasks import (
    NotificationPrefsOut, NotificationPrefsPatch, PushSubscribeRequest, PushTestOut, PushUnsubscribeRequest,
    VapidKeyOut,
)
from app.security import get_current_user_id
from app.services.notifications_service import NotificationsService

router = APIRouter(prefix="/notifications", tags=["notifications"], dependencies=[Depends(rate_limit("api"))])


async def _prefs_out(user_id: UUID, service: NotificationsService) -> NotificationPrefsOut:
    prefs, devices, available = await service.status(user_id)
    return NotificationPrefsOut(
        push_enabled=prefs.push_enabled, quiet_start=prefs.quiet_start, quiet_end=prefs.quiet_end,
        nudge_hour=prefs.nudge_hour, max_per_day=prefs.max_per_day, devices=devices, push_available=available,
    )


@router.get("/vapid-key", response_model=VapidKeyOut)
async def vapid_key(settings: Settings = Depends(get_settings)) -> VapidKeyOut:
    """The public half only. null = push isn't configured on this server."""
    return VapidKeyOut(public_key=settings.vapid_public_key or None)


@router.get("/prefs", response_model=NotificationPrefsOut)
async def get_prefs(
    user_id: UUID = Depends(get_current_user_id),
    service: NotificationsService = Depends(get_notifications_service),
) -> NotificationPrefsOut:
    return await _prefs_out(user_id, service)


@router.patch("/prefs", response_model=NotificationPrefsOut)
async def patch_prefs(
    body: NotificationPrefsPatch,
    user_id: UUID = Depends(get_current_user_id),
    service: NotificationsService = Depends(get_notifications_service),
) -> NotificationPrefsOut:
    await service.update_prefs(user_id, {k: getattr(body, k) for k in body.model_fields_set})
    return await _prefs_out(user_id, service)


@router.put("/subscription", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def subscribe(
    body: PushSubscribeRequest,
    user_agent: str | None = Header(None),
    user_id: UUID = Depends(get_current_user_id),
    service: NotificationsService = Depends(get_notifications_service),
) -> Response:
    await service.subscribe(user_id, body.endpoint, body.keys.p256dh, body.keys.auth, user_agent)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/subscription", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def unsubscribe(
    body: PushUnsubscribeRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: NotificationsService = Depends(get_notifications_service),
) -> Response:
    await service.unsubscribe(user_id, body.endpoint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/test", response_model=PushTestOut,
    dependencies=[Depends(rate_limit("push_test", limit_setting="rate_limit_push_test_per_hour", window_seconds=3600))],
)
async def send_test(
    user_id: UUID = Depends(get_current_user_id),
    service: NotificationsService = Depends(get_notifications_service),
) -> PushTestOut:
    return PushTestOut(delivered=await service.send_test(user_id))
