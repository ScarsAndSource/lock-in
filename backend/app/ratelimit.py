"""
Per-user rate limiting.

Two layers, same call signatures as before:
  * rate_limit(bucket, ...)  the FastAPI dependency. The cheap, high-volume "api" bucket stays in-process (a Redis
    round trip on every request buys nothing for it). Every other bucket (chat is handled in limits/turn.py,
    media, capture, export, calendar import, ...) is a Redis GCRA bucket, shared across instances and restarts.
  * SlidingWindowLimiter     the in-process limiter. It is the fallback whenever Redis is unset or unreachable,
    so with no REDIS_URL behaviour is exactly what it was.

Scope, stated plainly: the in-process state lives in this process. Pre-auth abuse is not covered here (put
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
from app.limits import gcra, strikes
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

# Buckets that stay in-process even when Redis is configured.
_LOCAL_ONLY = frozenset({"api"})


def get_limiter() -> SlidingWindowLimiter:
    return _limiter


def enforce_media_limits(user_id: UUID, settings: Settings) -> None:
    """Voice and screenshot uploads share one per-minute and one per-hour budget (they cost a model call each)."""
    if not settings.rate_limit_enabled:
        return
    for bucket, limit, window in (
        ("media_min", settings.rate_limit_media_per_minute, 60),
        ("media_hour", settings.rate_limit_media_per_hour, 3600),
    ):
        retry_after = get_limiter().check(f"{bucket}:{user_id}", limit, window)
        if retry_after is not None:
            raise RateLimitedError(retry_after)


def rate_limit(
    bucket: str,
    *,
    limit_setting: str = "rate_limit_per_minute",
    window_seconds: int = 60,
    burst: int | None = None,
):
    async def _dependency(
        user_id: UUID = Depends(get_current_user_id),
        settings: Settings = Depends(get_settings),
    ) -> None:
        if not settings.rate_limit_enabled:
            return
        limit = getattr(settings, limit_setting)
        if bucket in _LOCAL_ONLY:
            retry_after = get_limiter().check(f"{bucket}:{user_id}", limit, window_seconds)
        else:
            scale = await strikes.cap_scale(user_id)                  # 0.5 while the person's AI limits are halved
            retry_after = await gcra.check(str(user_id), [
                gcra.Bucket(bucket, strikes.scaled(limit, scale), window_seconds,
                            None if burst is None else strikes.scaled(burst, scale)),
            ])
        if retry_after is not None:
            if bucket not in _LOCAL_ONLY:
                await strikes.note_limited(user_id, bucket)
            raise RateLimitedError(retry_after)

    return _dependency
