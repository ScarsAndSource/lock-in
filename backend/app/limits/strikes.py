"""
Abuse strikes: turn repeated detections into proportionate, self-healing consequences. AI features only.

A detection (an injection attempt, a reply that leaks the prompt or carries a link, a burst of 429s) adds weighted
strikes to a per-user sorted set. Strikes older than strike_window_seconds fall out on their own, so a one-off costs
nothing and an honest user who trips a false positive now and then never reaches a threshold.

  soft threshold  AI rate limits halve for strike_halve_seconds (cap_scale() = 0.5)
  hard threshold  AI is switched off for the person (the same ban flag the operator switch uses): the first time for
                  strike_ban_first_seconds, after that for strike_ban_repeat_seconds, and from strike_review_offenses
                  offenses on the event is also flagged for review (audit severity "review" + a Sentry message)

What this never touches: the crisis path, manual logging, tasks, undo, reads. Those don't go through an AI gate at all.
Redis is volatile and optional: with it unavailable nothing is counted or enforced (the audit log line is still written),
and record()/note_limited() never raise: a failure here must not fail the request that was being protected.
"""
from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app import audit, observability
from app.config import get_settings
from app.limits import aigate
from app.redis_client import key, safe

logger = logging.getLogger("lockin.strikes")

# How much each detection is worth. Kept out of settings on purpose: these are code-level judgements about signals.
WEIGHTS = {
    "injection_contained": 1,
    "injection_blocked": 2,
    "output_rejected": 1,
    "prompt_leak": 2,
    "rate_limit_storm": 1,
}


@dataclass(frozen=True, slots=True)
class StrikeState:
    level: int = 0            # 0 normal, 1 caps halved, 2 AI switched off
    count: int = 0            # strikes currently in the window (0 when Redis is unavailable)
    ban_seconds: int = 0
    offense: int = 0


def _zset(user_id: UUID | str) -> str:
    return key("strk", user_id)


def _halved(user_id: UUID | str) -> str:
    return key("strk_half", user_id)


def _offenses(user_id: UUID | str) -> str:
    return key("strk_off", user_id)


async def record(
    user_id: UUID | str, kind: str, *, weight: int | None = None, meta: dict[str, Any] | None = None,
) -> StrikeState:
    """Add strikes for one detection and apply any consequence. Never raises."""
    try:
        s = get_settings()
        w = max(1, weight if weight is not None else WEIGHTS.get(kind, 1))
        await audit.emit(kind, user_id=user_id, severity="info", meta={**(meta or {}), "weight": w})

        now_ms = int(time.time() * 1000)
        zk = _zset(user_id)
        members = {f"{now_ms}:{kind}:{secrets.token_hex(3)}:{i}": now_ms for i in range(w)}

        async def add(r):
            pipe = r.pipeline(transaction=True)
            pipe.zadd(zk, members)
            pipe.zremrangebyscore(zk, 0, now_ms - s.strike_window_seconds * 1000)
            pipe.zcard(zk)
            pipe.expire(zk, s.strike_window_seconds)
            return int((await pipe.execute())[2])

        count = await safe(add, None)
        if count is None:                      # Redis unavailable: detection is logged, nothing is enforced
            return StrikeState()
        if count >= s.strike_hard_threshold:
            return await _switch_off(user_id, count)
        if count >= s.strike_soft_threshold:
            newly = await safe(lambda r: r.set(_halved(user_id), b"1", ex=s.strike_halve_seconds, nx=True), None)
            if not newly:
                await safe(lambda r: r.expire(_halved(user_id), s.strike_halve_seconds), None)
            else:
                await audit.emit("caps_halved", user_id=user_id, severity="warn", meta={"strikes": count})
            return StrikeState(level=1, count=count)
        return StrikeState(count=count)
    except Exception:  # noqa: BLE001
        logger.exception("strike bookkeeping failed")
        return StrikeState()


async def _switch_off(user_id: UUID | str, count: int) -> StrikeState:
    s = get_settings()
    zk, hk, ok = _zset(user_id), _halved(user_id), _offenses(user_id)

    async def apply(r):
        pipe = r.pipeline(transaction=True)
        pipe.incr(ok)
        pipe.expire(ok, s.strike_offense_memory_seconds)
        offense = int((await pipe.execute())[0])
        seconds = s.strike_ban_first_seconds if offense == 1 else s.strike_ban_repeat_seconds
        pipe = r.pipeline(transaction=True)
        pipe.set(aigate.ban_key(user_id), b"1", ex=seconds)
        pipe.delete(zk, hk)                    # a fresh window after the ban, so it can't re-trigger instantly
        await pipe.execute()
        return offense, seconds

    got = await safe(apply, None)
    if got is None:
        return StrikeState(count=count)
    offense, seconds = got
    review = offense >= s.strike_review_offenses
    await audit.emit(
        "ai_off", user_id=user_id, severity="review" if review else "high",
        meta={"strikes": count, "offense": offense, "seconds": seconds},
    )
    if review:
        observability.report(f"AI-abuse review: a user reached offense {offense} (see ai_security_events)", "warning")
    return StrikeState(level=2, count=count, ban_seconds=seconds, offense=offense)


async def cap_scale(user_id: UUID | str) -> float:
    """1.0 normally, 0.5 while the person's AI limits are halved. One cheap GET."""
    flagged = await safe(lambda r: r.get(_halved(user_id)), None)
    return 0.5 if flagged else 1.0


def scaled(limit: int, scale: float) -> int:
    return max(1, int(limit * scale))


async def note_limited(user_id: UUID | str, bucket: str) -> None:
    """Call when someone is rate limited. A burst of these inside the storm window counts as ONE strike."""
    try:
        s = get_settings()
        if s.strike_storm_threshold <= 0:
            return
        k = key("rl429", user_id)

        async def bump(r):
            n = int(await r.incr(k))
            if n == 1:
                await r.expire(k, s.strike_storm_window_seconds)
            if n == s.strike_storm_threshold:
                await r.delete(k)
            return n

        n = await safe(bump, None)
        if n == s.strike_storm_threshold:
            await record(user_id, "rate_limit_storm", meta={"bucket": bucket})
    except Exception:  # noqa: BLE001
        logger.exception("429 storm bookkeeping failed")
