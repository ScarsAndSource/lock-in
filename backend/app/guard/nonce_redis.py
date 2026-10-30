"""
Shared single-use store for signed card tokens (confirm and undo).

The in-process store only knows about tokens used on THIS process, so after a restart or on a second instance a used
card could be applied again until it expires (about 10 minutes): a duplicate task, a double undo. Here the first use
of a nonce wins across every instance: SET key NX EX <seconds left on the token>. The key expires on its own when the
token would have, so nothing accumulates.

Redis unset or unreachable => the in-process store answers instead (same behaviour as before this file existed: single
use per process). The one window this leaves: a token used while Redis was down can be used once more after it is back.
release() undoes a consume after a transient failure so the person can tap again; if Redis is down at that moment the
card stays used and they simply ask again.
"""
from __future__ import annotations

import math
from datetime import datetime

from app.guard.signing import InMemoryNonceStore, NonceStore
from app.redis_client import key, safe

_NA = object()
_GRACE_SECONDS = 5      # outlive the token slightly so clock skew between instances can't reopen it early


class RedisNonceStore:
    def __init__(self, fallback: NonceStore | None = None):
        self._fallback: NonceStore = fallback if fallback is not None else InMemoryNonceStore()

    async def consume(self, nonce: str, expires_at: datetime, now: datetime) -> bool:
        ttl = max(1, math.ceil((expires_at - now).total_seconds())) + _GRACE_SECONDS
        got = await safe(lambda r: r.set(key("nonce", nonce), b"1", nx=True, ex=ttl), _NA)
        if got is _NA:                                   # Redis off or unreachable
            return await self._fallback.consume(nonce, expires_at, now)
        return bool(got)                                 # True the first time, None (replay) -> False

    async def release(self, nonce: str) -> None:
        await safe(lambda r: r.delete(key("nonce", nonce)), None)
        await self._fallback.release(nonce)
