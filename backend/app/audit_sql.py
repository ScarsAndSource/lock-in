"""
The database side of app/audit.py. Kept apart so audit.py (and everything that calls it) imports no database code.

Writes on its own short session as the connection's owner role: ai_security_events has RLS enabled and NO policy, so
the app's `authenticated` role (every user request) can neither read nor write it. Only this sink and the operator's
jobs can.
"""
from __future__ import annotations

import json

from sqlalchemy import text

from app.audit import AuditEvent
from app.db import AsyncSessionLocal

_INSERT = text(
    "insert into public.ai_security_events (user_id, kind, severity, meta, request_id, created_at) "
    "values (:user_id, :kind, :severity, cast(:meta as jsonb), :request_id, :created_at)"
)


async def write_event(event: AuditEvent) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(_INSERT, {
                "user_id": event.user_id, "kind": event.kind, "severity": event.severity,
                "meta": json.dumps(event.meta, sort_keys=True), "request_id": event.request_id,
                "created_at": event.created_at,
            })
