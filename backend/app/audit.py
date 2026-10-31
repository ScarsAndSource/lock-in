"""
Security audit trail for the AI layer: what was detected, never what was said.

Every event is one structured log line (always) and, when a sink is installed (the API installs one at startup), one
row in ai_security_events (migration 028). An event carries a kind, a severity, the user id, the request id and a few
SAFE meta values: counts, category codes, and keyed hashes. Free text can't get in: clean_meta() drops every value that
isn't a number, a boolean or a short token of letters/digits/punctuation, so a prompt that slips into meta by mistake is
dropped instead of stored. digest() is a keyed HMAC: the same message gives the same value (so a repeated attack can be
correlated) but nobody can guess a short message from it.

emit() never raises and never blocks the request: the database write runs as a background task, bounded so a slow
database can't pile up tasks (the log line is still written).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.config import get_settings

logger = logging.getLogger("lockin.security")

SEVERITIES = ("info", "warn", "high", "review")
MAX_META_KEYS = 12
MAX_PENDING_WRITES = 50

request_id_var: ContextVar[str | None] = ContextVar("lockin_request_id", default=None)

_KEY = re.compile(r"^[a-z0-9_]{1,24}$")
_VALUE = re.compile(r"^[A-Za-z0-9_.:,@/\-]{0,64}$")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    kind: str
    severity: str
    user_id: UUID | None
    request_id: str | None
    meta: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


Sink = Callable[[AuditEvent], Awaitable[None]]
_sink: Sink | None = None
_pending: set[asyncio.Task] = set()


def set_sink(sink: Sink | None) -> None:
    global _sink
    _sink = sink


def digest(text: str) -> str:
    """Keyed, truncated hash of a piece of text: correlate repeats without storing or exposing the text."""
    key = hmac.new(get_settings().field_encryption_key.encode("utf-8"), b"lockin/audit-digest/v1", hashlib.sha256).digest()
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def clean_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (meta or {}).items():
        if len(out) >= MAX_META_KEYS:
            break
        if not isinstance(k, str) or not _KEY.match(k):
            continue
        if isinstance(v, bool) or isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str) and _VALUE.match(v):
            out[k] = v
    return out


def _forget(task: asyncio.Task) -> None:
    _pending.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.warning("audit sink failed: %s", type(task.exception()).__name__)


async def emit(
    kind: str, *, user_id: UUID | str | None = None, severity: str = "info", meta: dict[str, Any] | None = None,
) -> None:
    try:
        uid: UUID | None = None
        if user_id is not None:
            uid = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
        event = AuditEvent(
            kind=kind[:48], severity=severity if severity in SEVERITIES else "info", user_id=uid,
            request_id=request_id_var.get(), meta=clean_meta(meta),
        )
        logger.log(
            logging.WARNING if event.severity in ("high", "review") else logging.INFO,
            "ai_security_event %s",
            json.dumps({
                "kind": event.kind, "severity": event.severity, "user": str(uid) if uid else None,
                "request_id": event.request_id, "meta": event.meta,
            }, sort_keys=True),
        )
        if _sink is not None and len(_pending) < MAX_PENDING_WRITES:
            task = asyncio.get_running_loop().create_task(_sink(event))
            _pending.add(task)
            task.add_done_callback(_forget)
    except Exception:  # noqa: BLE001 -- an audit failure must never fail the request it describes
        logger.exception("audit emit failed")
