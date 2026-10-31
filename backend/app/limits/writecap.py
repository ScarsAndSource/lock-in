"""
Auto-apply ceilings: how many writes the chat agent may make for a person WITHOUT asking, per minute and per day.

The agent already refuses to write anything the person's own words don't support (guard/grounding.py) and holds bulk
edits back (bulk_guard). This is the last wall behind those: even if a model, a hostile import or a scripted client
produced a flood of plausible-looking actions, only the first few land silently. Past the ceiling an action is not
dropped and not applied: it comes back as a PENDING card (one tap to confirm, re-validated on confirm), exactly like an
ambiguous one. So an honest burst (a morning brain-dump) costs a few taps; an attack costs the attacker nothing it
could keep.

  per minute   GCRA bucket (app/limits/gcra.py), burst = the limit, so ten quick writes are fine and the eleventh waits
  per day      a UTC-day counter in Redis; in-process while Redis is unavailable (per instance, resets on restart)

All-or-nothing: a refusal by one ceiling never spends the other. Only unconfirmed (auto-applied) writes are counted:
a tap on a confirm card is the person acting, so it is never capped here. reserve() never raises and fails open: a
bookkeeping failure must not stop a write the person is entitled to. Settings: autoapply_per_day, autoapply_per_minute
(0 turns that ceiling off); everything is off with RATE_LIMIT_ENABLED=false.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from app import audit
from app.config import get_settings
from app.limits import gcra
from app.redis_client import key, safe

logger = logging.getLogger("lockin.writecap")

CAP_REASON = "That's a lot of changes in a short time. Tap to confirm this one."

_TTL_SECONDS = 2 * 86400
_MEMORY_LIMIT = 5000                 # distinct (day, user) counters kept in-process before the table is reset

_memory: dict[str, int] = {}


def _bump_memory(counter_key: str) -> int:
    if len(_memory) >= _MEMORY_LIMIT and counter_key not in _memory:
        _memory.clear()              # only ever loosens the ceiling a little; Redis is the real store
    _memory[counter_key] = _memory.get(counter_key, 0) + 1
    return _memory[counter_key]


async def _incr_day(counter_key: str) -> int | None:
    async def op(r):
        pipe = r.pipeline(transaction=True)
        pipe.incr(counter_key)
        pipe.expire(counter_key, _TTL_SECONDS)
        return int((await pipe.execute())[0])

    return await safe(op, None)


async def _undo_day(counter_key: str, in_redis: bool) -> None:
    if in_redis:
        await safe(lambda r: r.decr(counter_key), None)
    else:
        _memory[counter_key] = max(0, _memory.get(counter_key, 1) - 1)


async def _refused(user_id: UUID | str, window: str) -> None:
    await audit.emit("autoapply_cap", user_id=user_id, severity="info", meta={"window": window})


async def reserve(user_id: UUID | str, *, now: datetime | None = None) -> str | None:
    """None = go ahead (one auto-apply is now reserved). Otherwise CAP_REASON: make this action a pending card."""
    try:
        s = get_settings()
        per_day, per_minute = s.autoapply_per_day, s.autoapply_per_minute
        if not s.rate_limit_enabled or (per_day <= 0 and per_minute <= 0):
            return None
        uid = str(user_id)
        in_redis = False
        day_key = key("wcap", (now or datetime.now(timezone.utc)).strftime("%Y%m%d"), uid)

        if per_day > 0:
            used = await _incr_day(day_key)
            if used is None:
                used = _bump_memory(day_key)
            else:
                in_redis = True
            if used > per_day:
                await _undo_day(day_key, in_redis)
                await _refused(user_id, "day")
                return CAP_REASON

        if per_minute > 0:
            retry_after = await gcra.check(uid, [gcra.Bucket("wcap_min", per_minute, 60)])
            if retry_after is not None:
                if per_day > 0:
                    await _undo_day(day_key, in_redis)
                await _refused(user_id, "minute")
                return CAP_REASON
        return None
    except Exception:  # noqa: BLE001 -- fail open: never block a legitimate write over bookkeeping
        logger.exception("auto-apply ceiling bookkeeping failed")
        return None
