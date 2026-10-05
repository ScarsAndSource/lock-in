"""
Per-user sliding-window rate limiting (in-memory).

Scope, stated plainly: state lives in this process. One Render instance = exact.
Several workers/instances = each enforces its own window (limit is multiplied).
When the Groq endpoints land, swap SlidingWindowLimiter for a Redis-backed one
with the same .check() signature. Pre-auth abuse is not covered here (put
Cloudflare/Render protections in front for that).
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from uuid import UUID

from fastapi import Depends

from app.config import Settings, get_settings
from app.exceptions import RateLimitedError
from app.security import get_current_user_id


class SlidingWindowLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._windows: dict[str, int] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def check(self, key: str, limit: int, window_seconds: int) -> int | None:
        """None if allowed (and recorded); else seconds until the next slot frees up."""
        now = self._clock()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            self._windows[key] = window_seconds
            cutoff = now - window_seconds
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= limit:
                return max(1, math.ceil(q[0] + window_seconds - now))
            q.append(now)
            self._calls += 1
            if self._calls % 1000 == 0:
                self._sweep(now)
            return None

    def _sweep(self, now: float) -> None:
        # Each key is judged against ITS OWN window (an hourly key must survive a minute of idleness).
        stale = [k for k, q in self._hits.items() if not q or q[-1] <= now - self._windows[k]]
        for k in stale:
            del self._hits[k]
            del self._windows[k]


_limiter = SlidingWindowLimiter()


def get_limiter() -> SlidingWindowLimiter:
    return _limiter


def rate_limit(bucket: str, *, limit_setting: str = "rate_limit_per_minute", window_seconds: int = 60):
    async def _dependency(
        user_id: UUID = Depends(get_current_user_id),
        settings: Settings = Depends(get_settings),
    ) -> None:
        if not settings.rate_limit_enabled:
            return
        retry_after = get_limiter().check(f"{bucket}:{user_id}", getattr(settings, limit_setting), window_seconds)
        if retry_after is not None:
            raise RateLimitedError(retry_after)

    return _dependency
