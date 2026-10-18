"""
Web push delivery. The sender is a tiny protocol so the nudge logic never touches the network in tests.

Privacy: payloads (task titles) and subscription keys are never logged; only HTTP status codes are.
SSRF: a subscription endpoint is a URL this server will POST to, so validate_endpoint() only lets through https
URLs on a known push-service host (list lives in settings, not code).
"""
from __future__ import annotations

import asyncio
import json
import logging
from enum import Enum
from typing import Protocol
from urllib.parse import urlsplit

from app.domain import PushSubscription
from app.exceptions import ValidationError

logger = logging.getLogger("lockin.push")


class PushOutcome(str, Enum):
    OK = "ok"
    GONE = "gone"            # 404/410: the browser dropped the subscription -> delete it
    FAILED = "failed"        # push service rejected THIS subscription (HTTP 400) -> count a strike
    TRANSIENT = "transient"  # bad VAPID key, outage, 401/403/429/5xx, network -> keep, no strike


class PushSender(Protocol):
    @property
    def configured(self) -> bool: ...

    async def send(self, sub: PushSubscription, payload: dict) -> PushOutcome: ...


def validate_endpoint(endpoint: str, allowed_suffixes: list[str]) -> str:
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        raise ValidationError("Push endpoint must be an https URL.")
    if parts.port not in (None, 443):
        raise ValidationError("Push endpoint must use the default https port.")
    if not any(host == s or host.endswith("." + s) for s in (x.lower().lstrip(".") for x in allowed_suffixes)):
        raise ValidationError("That isn't a supported browser push service.")
    return endpoint


class WebPushSender:
    def __init__(self, private_key: str, subject: str, ttl_seconds: int = 3600, timeout: float = 10.0):
        self._key, self._subject, self._ttl, self._timeout = private_key, subject, ttl_seconds, timeout

    @property
    def configured(self) -> bool:
        return bool(self._key and self._subject)

    async def send(self, sub: PushSubscription, payload: dict) -> PushOutcome:
        if not self.configured:
            return PushOutcome.TRANSIENT
        return await asyncio.to_thread(self._send_sync, sub, json.dumps(payload))

    def _send_sync(self, sub: PushSubscription, data: str) -> PushOutcome:
        from pywebpush import WebPushException, webpush  # imported lazily: the HTTP app doesn't need it to boot

        try:
            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=data,
                vapid_private_key=self._key,
                vapid_claims={"sub": self._subject},   # fresh dict every call: pywebpush mutates it
                ttl=self._ttl,
                timeout=self._timeout,
            )
            return PushOutcome.OK
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                return PushOutcome.GONE
            logger.warning("push failed (HTTP %s)", status)
            return PushOutcome.FAILED if status == 400 else PushOutcome.TRANSIENT
        except Exception:  # noqa: BLE001 -- a bad key / network error must never crash the whole run
            logger.warning("push failed (%s)", "unexpected error")
            return PushOutcome.TRANSIENT


class DisabledSender:
    """Used when VAPID isn't configured: the app works, nothing is sent."""
    configured = False

    async def send(self, sub: PushSubscription, payload: dict) -> PushOutcome:
        return PushOutcome.TRANSIENT
