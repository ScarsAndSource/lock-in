"""
Global AI ceiling: a daily limit on provider calls and tokens across ALL users, so a bug, an attack from many accounts,
or a runaway loop can't empty the free-tier quota (or the bill). When either counter reaches ai_global_trip_fraction
(default 90%) of its cap the global AI-off flag is set until 00:00 UTC, with an audit event and a Sentry message.
Every feature then takes its deterministic fallback, exactly as for the operator's `ai_switch pause`.

Both caps default to 0 = off, so nothing changes until you choose numbers (see python -m app.jobs.llm_usage_report for
what a normal day looks like). SET NX: an operator pause that is already in place is never shortened or replaced, and
`ai_switch resume` clears a trip. Redis unavailable = not counted (the per-user caps still apply). Never raises.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app import audit, observability
from app.config import get_settings
from app.limits import aigate
from app.redis_client import key, safe

logger = logging.getLogger("lockin.ceiling")
_TTL_SECONDS = 2 * 86400


def seconds_until_utc_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))


async def note(calls: int = 0, tokens: int = 0, *, now: datetime | None = None) -> bool:
    """Count one finished provider call. True if this call tripped the ceiling."""
    try:
        s = get_settings()
        cap_calls, cap_tokens = s.ai_global_daily_calls, s.ai_global_daily_tokens
        if (cap_calls <= 0 and cap_tokens <= 0) or (calls <= 0 and tokens <= 0):
            return False
        now = now or datetime.now(timezone.utc)
        day = now.strftime("%Y%m%d")
        kc, kt = key("gbud", day, "c"), key("gbud", day, "t")

        async def count(r):
            pipe = r.pipeline(transaction=True)
            pipe.incrby(kc, max(0, calls))
            pipe.expire(kc, _TTL_SECONDS)
            pipe.incrby(kt, max(0, tokens))
            pipe.expire(kt, _TTL_SECONDS)
            res = await pipe.execute()
            return int(res[0]), int(res[2])

        got = await safe(count, None)
        if got is None:
            return False
        used_calls, used_tokens = got
        fraction = s.ai_global_trip_fraction
        over = (cap_calls > 0 and used_calls >= cap_calls * fraction) or (cap_tokens > 0 and used_tokens >= cap_tokens * fraction)
        if not over:
            return False
        ttl = seconds_until_utc_midnight(now) + 60
        newly = await safe(lambda r: r.set(aigate.global_key(), b"1", nx=True, ex=ttl), None)
        if newly:
            message = f"Global AI ceiling reached: {used_calls} calls, {used_tokens} tokens today. AI is off until 00:00 UTC."
            logger.error(message)
            observability.report(message, "error")
            await audit.emit(
                "ai_global_ceiling", severity="high",
                meta={"calls": used_calls, "tokens": used_tokens, "cap_calls": cap_calls, "cap_tokens": cap_tokens},
            )
        return bool(newly)
    except Exception:  # noqa: BLE001
        logger.exception("global ceiling bookkeeping failed")
        return False
