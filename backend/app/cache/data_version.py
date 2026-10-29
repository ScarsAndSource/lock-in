"""
Per-user DATA VERSION: a counter that moves whenever the user's logged data may have changed.

Cached evidence packs are stored together with the version they were built at and are only reused while the counter is
unchanged, so a write invalidates them instantly (the TTL is just the safety net).

Who bumps it, always AFTER the transaction committed:
  * db.get_db            any POST/PUT/PATCH/DELETE (except the chat endpoints, below)
  * ingest + push-action the two token-auth paths that open their own sessions
  * the chat endpoints   POST /chat and /chat/messages mostly only READ, so they must not bump on every turn; the
                         agent calls mark_dirty() when it actually writes, and get_db then bumps after the commit

mark_dirty() also makes the REST of that request bypass the cache (reads and writes): the agent's follow-up answer has
to see the rows it just flushed, and facts built from uncommitted data must never be shared with other requests.
The flag is a ContextVar, so it lives and dies with the request's task.
"""
from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID

from app.redis_client import key, safe

_TTL_SECONDS = 30 * 86400
_BUMP = "local v = redis.call('INCR', KEYS[1]); redis.call('EXPIRE', KEYS[1], ARGV[1]); return v"

_dirty: ContextVar[bool] = ContextVar("lockin_data_dirty", default=False)


def key_for(user_id: UUID | str) -> str:
    return key("dv", user_id)


def mark_dirty() -> None:
    _dirty.set(True)


def is_dirty() -> bool:
    return _dirty.get()


async def bump(user_id: UUID) -> None:
    await safe(lambda r: r.eval(_BUMP, 1, key_for(user_id), _TTL_SECONDS), None)
