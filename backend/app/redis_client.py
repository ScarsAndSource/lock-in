"""
One shared async Redis client, built for FAILING OPEN.

Everything that uses Redis in this app (rate limits, the in-flight chat lock, idempotency, the AI kill-switch and
breaker) goes through safe(). If Redis is unset, slow or down, safe() hands back the caller's default and the caller
uses its in-process fallback, so a Redis outage degrades limits from "shared" to "per instance" and never takes the
app down. After a failure Redis is skipped for a few seconds so a dead server costs one timeout, not one per request.

Rules:
  * Redis holds only things that can be lost: counters, locks, cached replies, flags. Run it without persistence.
  * Values that carry user text (idempotent replies) are encrypted before they get here (see limits/idempotency.py).
  * The crisis/support path never calls into this module.
  * Logs name the exception type only (a Redis error message can contain the host).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import get_settings

logger = logging.getLogger("lockin.redis")

T = TypeVar("T")

_COOL_OFF_SECONDS = 5.0

_client: Redis | None = None
_client_loop: asyncio.AbstractEventLoop | None = None
_down_until = 0.0


def key(*parts: object) -> str:
    """lk:<env>:a:b:c -- one namespace per environment, so staging and prod can share a Redis safely."""
    return ":".join(["lk", get_settings().app_env, *(str(p) for p in parts)])


def get_redis() -> Redis | None:
    """The shared client, or None when Redis is not configured / is in its cool-off after a failure."""
    global _client, _client_loop
    settings = get_settings()
    if not settings.redis_url:
        return None
    if time.monotonic() < _down_until:
        return None
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:  # a client is bound to its event loop (matters for tests)
        _client = Redis.from_url(
            settings.redis_url,
            socket_timeout=settings.redis_socket_timeout_seconds,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
            health_check_interval=30,
            max_connections=settings.redis_max_connections,
            decode_responses=False,
        )
        _client_loop = loop
    return _client


def _trip(exc: BaseException) -> None:
    global _down_until
    now = time.monotonic()
    if now >= _down_until:
        logger.warning(
            "Redis unavailable (%s); using in-process limits for %.0fs", type(exc).__name__, _COOL_OFF_SECONDS,
        )
    _down_until = now + _COOL_OFF_SECONDS


async def safe(op: Callable[[Redis], Awaitable[T]], default: T) -> T:
    """Run one Redis operation. Any Redis/network/timeout failure -> `default` (the caller's fallback signal)."""
    client = get_redis()
    if client is None:
        return default
    try:
        return await op(client)
    except (RedisError, OSError, asyncio.TimeoutError) as exc:
        _trip(exc)
        return default


async def close_redis() -> None:
    global _client, _client_loop
    client, _client, _client_loop = _client, None, None
    if client is not None:
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001 -- shutting down, nothing to do about it
            pass
