"""
AI kill-switch + circuit breaker, checked before EVERY model call (BudgetedLLM._metered).

blocked_reason(user_id) -> None (go ahead) or why the call must not happen:
  "breaker"  the provider has been failing; calls are refused instantly instead of each hanging for the timeout
  "paused"   global kill-switch: the operator turned AI off for everyone
  "banned"   this one user is switched off (AI only: the tracker, undo and the crisis path keep working)
The caller turns any reason into LLMUnavailableError, so every feature takes its existing deterministic fallback.
One Redis round trip answers all three (MGET).

Breaker: failures are counted PER INSTANCE in memory; when this instance trips, the OPEN flag is also written to Redis
so every instance stops calling the provider. After the cooldown the flag expires and calls resume; the first failure
after that re-opens immediately (half-open, though not single-probe: concurrent calls all go through). Only
LLMUnavailableError counts (timeout, 5xx, 429 after retries, bad credentials); a malformed reply or a 400 is not the
provider being down.

Redis is volatile: a global pause or a ban set here disappears if Redis restarts. Durable bans belong in the database.
Operate it with: python -m app.jobs.ai_switch
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from uuid import UUID

from app.config import get_settings
from app.redis_client import get_redis, key, safe

logger = logging.getLogger("lockin.aigate")


def global_key() -> str:
    return key("flag", "ai_off")


def ban_key(user_id: UUID | str) -> str:
    return key("ban", user_id)


def open_key() -> str:
    return key("brk", "open")


@dataclass
class _Local:
    fails: deque[float] = field(default_factory=deque)
    open_until: float = 0.0
    half_open: bool = False


_local = _Local()


# ---------------------------------------------------------------- the check
async def blocked_reason(user_id: UUID) -> str | None:
    if time.monotonic() < _local.open_until:
        return "breaker"
    vals = await safe(lambda r: r.mget(global_key(), ban_key(user_id), open_key()), None)
    if not vals:
        return None
    if vals[0] is not None:
        return "paused"
    if vals[1] is not None:
        return "banned"
    if vals[2] is not None:
        return "breaker"
    return None


# ---------------------------------------------------------------- breaker bookkeeping
def record_success() -> None:
    _local.fails.clear()
    _local.half_open = False


async def record_failure() -> None:
    s = get_settings()
    now = time.monotonic()
    if now < _local.open_until:
        return  # already open; late failures from calls that were in flight don't extend it
    while _local.fails and _local.fails[0] <= now - s.ai_breaker_window_seconds:
        _local.fails.popleft()
    _local.fails.append(now)
    if _local.half_open or len(_local.fails) >= s.ai_breaker_failures:
        cooldown = s.ai_breaker_cooldown_seconds
        _local.fails.clear()
        _local.half_open = True
        _local.open_until = now + cooldown
        logger.warning("AI breaker OPEN for %ss", cooldown)
        await safe(lambda r: r.set(open_key(), b"1", ex=cooldown), None)


# ---------------------------------------------------------------- operator controls (CLI; errors propagate)
def _require():
    client = get_redis()
    if client is None:
        raise RuntimeError("Redis is not configured or is unreachable right now (set REDIS_URL).")
    return client


async def pause_all(ttl_seconds: int | None = None) -> None:
    await _require().set(global_key(), b"1", ex=ttl_seconds)


async def resume_all() -> None:
    await _require().delete(global_key())


async def ban_user(user_id: UUID, ttl_seconds: int) -> None:
    await _require().set(ban_key(user_id), b"1", ex=ttl_seconds)


async def unban_user(user_id: UUID) -> None:
    await _require().delete(ban_key(user_id))


async def reset_breaker() -> None:
    _local.fails.clear()
    _local.half_open = False
    _local.open_until = 0.0
    await _require().delete(open_key())


async def status(user_id: UUID | None = None) -> dict:
    r = _require()

    async def ttl(k: str) -> int | None:
        v = await r.ttl(k)  # -2 = no such key, -1 = no expiry
        return None if v == -2 else v

    out = {"paused_ttl": await ttl(global_key()), "breaker_open_ttl": await ttl(open_key())}
    if user_id is not None:
        out["user_ban_ttl"] = await ttl(ban_key(user_id))
    return out
