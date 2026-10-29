"""
Short-lived mutex ("one chat turn in flight per user").

SET NX PX with a random token, released by a compare-and-delete script so a slow request can never free a lock that
has since been taken by someone else. If Redis is unavailable it uses a process-local table with the same TTL
semantics, so a double-tapped Send is still blocked on a single instance.

The TTL is the safety net, not the mechanism: the normal path always releases explicitly (limits/turn.py).
"""
from __future__ import annotations

import time
from uuid import uuid4

from app.redis_client import key, safe

_NA = object()
_RELEASE = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end"
)

_local: dict[str, tuple[str, float]] = {}


def _local_acquire(k: str, token: str, ttl_seconds: int) -> str | None:
    now = time.monotonic()
    if len(_local) > 1000:
        for stale in [name for name, (_, expires) in _local.items() if expires <= now]:
            del _local[stale]
    held = _local.get(k)
    if held is not None and held[1] > now:
        return None
    _local[k] = (token, now + ttl_seconds)
    return token


async def acquire(name: str, subject: str, ttl_seconds: int) -> str | None:
    """A token when the lock is yours, None when someone else holds it."""
    token = uuid4().hex
    k = key("lock", name, subject)
    got = await safe(lambda r: r.set(k, token, nx=True, ex=ttl_seconds), _NA)
    if got is _NA:
        return _local_acquire(k, token, ttl_seconds)
    return token if got else None


async def release(name: str, subject: str, token: str) -> None:
    k = key("lock", name, subject)
    held = _local.get(k)
    if held is not None and held[0] == token:
        del _local[k]
    await safe(lambda r: r.eval(_RELEASE, 1, k, token), None)
