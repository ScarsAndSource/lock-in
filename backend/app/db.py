"""
One request-scoped session, scoped to the authenticated user.

(1) COMMIT. Repositories only flush(); this dependency commits on success and rolls back on any exception, so a
    request's writes are atomic.
(2) RLS. A direct DB connection normally BYPASSES Row Level Security. With rls_enforced we set the Supabase JWT claims
    as transaction-local settings and `SET LOCAL ROLE authenticated`, so auth.uid() resolves and the policies really
    apply. It is done in an after_begin listener, so EVERY transaction the session starts gets it, including the one
    that begins after a mid-request release (below). SET LOCAL dies with the transaction -> pgbouncer-safe.
(3) DATA VERSION. After a COMMITTED write request the user's data version is bumped (app/cache/data_version.py), which
    instantly invalidates their cached evidence pack. An exception skips it (nothing was committed).
(4) CONNECTION RELEASE (batch 6). The chat and media routes (_RELEASE_PATHS) read first, call a model, then write. The
    model call can take seconds, and a transaction held across it pins a pooled connection the whole time. For those
    routes the session ends its (read-only) transaction right before the model call (app/dbrelease.py) and checks a
    connection out again at its next query. A request that has already written (data_version.is_dirty()) never
    releases, so the agent's writes and the stored reply stay one atomic transaction.
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import dbrelease
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
# Routes that only READ before a model call and write (if at all) after it: they hand the connection back first.
_RELEASE_PATHS = frozenset({
    "/chat/messages", "/checkins/parse", "/checkins/voice", "/screen-time/parse-screenshot", "/calendar/parse-image",
})

_RLS_SQL = (
    "select set_config('request.jwt.claims', :claims, true), "
    "set_config('request.jwt.claim.sub', :sub, true), "
    "set_config('request.jwt.claim.role', 'authenticated', true)"
)


def _rls_params(user_id: UUID) -> dict[str, str]:
    return {"claims": json.dumps({"sub": str(user_id), "role": "authenticated"}), "sub": str(user_id)}


async def apply_rls_context(session: AsyncSession, user_id: UUID) -> None:
    """For code that opens its own session (jobs, token-auth routes) and manages its own transaction."""
    await session.execute(text(_RLS_SQL), _rls_params(user_id))
    await session.execute(text("set local role authenticated"))


def _apply_rls_sync(connection, user_id: UUID) -> None:
    connection.execute(text(_RLS_SQL), _rls_params(user_id))
    connection.execute(text("set local role authenticated"))


def _listen_for_rls(session: AsyncSession, user_id: UUID) -> None:
    """Re-apply the RLS context at the start of every transaction this session begins."""

    @event.listens_for(session.sync_session, "after_begin")
    def _on_begin(_sync_session, _transaction, connection) -> None:
        _apply_rls_sync(connection, user_id)


async def get_db(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
    try:
        if settings.rls_enforced:
            _listen_for_rls(session, user_id)

        if request.url.path.rstrip("/") in _RELEASE_PATHS:
            async def release() -> None:
                if data_version.is_dirty() or not session.in_transaction() or session.in_nested_transaction():
                    return
                await session.commit()   # nothing was written: this only ends the transaction and frees the connection

            dbrelease.install(release)

        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    finally:
        dbrelease.clear()
        await session.close()
    # Only reached when the transaction committed.
    wrote = request.method in _WRITE_METHODS and request.url.path.rstrip("/") not in _SELF_MANAGED_PATHS
    if wrote or data_version.is_dirty():
        await data_version.bump(user_id)


async def ping_database() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("select 1"))
