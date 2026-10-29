"""
Weighted per-user daily budget in Redis, in front of the DB call cap (llm_usage stays the source of truth for calls).

The call cap treats a 400-token chat and a 1400-token photo parse as one call each. Two extra daily limits fix that:
  units   weighted calls (text 1, audio 2, vision 3). Reserved atomically BEFORE the call, refunded if the call doesn't
          happen (provider down, DB cap hit)
  tokens  provider-reported tokens, added AFTER each call; once the day's total reaches the cap, further calls are refused
Either limit set to 0 turns that limit off. With Redis unavailable both are skipped and the DB cap alone applies.
Days are UTC, like the DB cap. reserve() returns None (go ahead) or "units"/"tokens" (which limit was hit); the caller
raises LLMBudgetExceeded so every feature handles it exactly like the daily call cap.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from app.config import get_settings
from app.redis_client import key, safe

WEIGHT_TEXT = 1
WEIGHT_AUDIO = 2
WEIGHT_VISION = 3

_TTL_SECONDS = 2 * 86400

_RESERVE = """
local cap_u = tonumber(ARGV[1])
local cap_t = tonumber(ARGV[2])
local w = tonumber(ARGV[3])
local used_t = tonumber(redis.call('GET', KEYS[2]) or '0')
if cap_t > 0 and used_t >= cap_t then return 2 end
local u = redis.call('INCRBY', KEYS[1], w)
if u == w then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[4])) end
if cap_u > 0 and u > cap_u then
  redis.call('DECRBY', KEYS[1], w)
  return 1
end
return 0
"""

_ADD_TOKENS = """
local v = redis.call('INCRBY', KEYS[1], ARGV[1])
if v == tonumber(ARGV[1]) then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2])) end
return v
"""


def _k(user_id: UUID, day: date, suffix: str) -> str:
    return key("bud", user_id, day.strftime("%Y%m%d"), suffix)


def _enabled() -> bool:
    s = get_settings()
    return s.llm_daily_unit_cap > 0 or s.llm_daily_token_cap > 0


async def reserve(user_id: UUID, day: date, weight: int) -> str | None:
    if not _enabled():
        return None
    s = get_settings()
    code = await safe(
        lambda r: r.eval(
            _RESERVE, 2, _k(user_id, day, "u"), _k(user_id, day, "t"),
            s.llm_daily_unit_cap, s.llm_daily_token_cap, weight, _TTL_SECONDS,
        ),
        0,
    )
    return {1: "units", 2: "tokens"}.get(int(code))


async def refund(user_id: UUID, day: date, weight: int) -> None:
    if not _enabled():
        return
    await safe(lambda r: r.decrby(_k(user_id, day, "u"), weight), None)


async def add_tokens(user_id: UUID, day: date, tokens: int) -> None:
    if tokens <= 0 or get_settings().llm_daily_token_cap <= 0:
        return
    await safe(lambda r: r.eval(_ADD_TOKENS, 1, _k(user_id, day, "t"), tokens, _TTL_SECONDS), None)
