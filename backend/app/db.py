"""
One transaction per request, scoped to the authenticated user.

(1) COMMIT. Repositories only flush(); this dependency commits on success and
    rolls back on any exception, so a request's writes are atomic.
(2) RLS. A direct DB connection normally BYPASSES Row Level Security. With
    rls_enforced we set the Supabase JWT claims as transaction-local settings
    and `SET LOCAL ROLE authenticated`, so auth.uid() resolves and the policies
    really apply. SET LOCAL dies with the transaction -> pgbouncer-safe.
(3) DATA VERSION. After a COMMITTED write request the user's data version is bumped (app/cache/data_version.py), which
    instantly invalidates their cached evidence pack. An exception skips it (nothing was committed).
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.cache import data_version
from app.config import Settings, get_settings
from app.security import get_current_user_id

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_timeout=_settings.db_pool_timeout_seconds,   # a full pool answers 503 after this long, it never queues forever
    connect_args={"statement_cache_size": 0},  # required behind Supabase's pooler
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# The chat endpoints are POSTs that mostly only READ. They report their own writes with data_version.mark_dirty().
_SELF_MANAGED_PATHS = frozenset({"/chat", "/chat/messages"})


async def apply_rls_context(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(
        text(
            "select set_config('request.jwt.claims', :claims, true), "
            "set_config('request.jwt.claim.sub', :sub, true), "
            "set_config('request.jwt.claim.role', 'authenticated', true)"
        ),
        {"claims": json.dumps({"sub": str(user_id), "role": "authenticated"}), "sub": str(user_id)},
    )
    await session.execute(text("set local role authenticated"))


async def get_db(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        async with session.begin():  # commit on clean exit, rollback on exception
            if settings.rls_enforced:
                await apply_rls_context(session, user_id)
            yield session
    # Only reached when the transaction committed.
    wrote = request.method in _WRITE_METHODS and request.url.path.rstrip("/") not in _SELF_MANAGED_PATHS
    if wrote or data_version.is_dirty():
        await data_version.bump(user_id)


async def ping_database() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("select 1"))
