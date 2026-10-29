"""
GCRA ("leaky bucket as a meter") rate limiting, atomic in Redis via one Lua script.

Why GCRA instead of the old sliding window:
  * one number per key (the theoretical arrival time), so it is O(1) in memory and in Redis
  * bursts are allowed up to `burst`, then requests are spaced evenly: a person who sends three messages in a row is
    fine, a script that sends 60 a minute is not
  * several buckets are checked ALL-OR-NOTHING in one script: a request refused by the hourly bucket never burns a
    minute token (the old per-bucket loop did)

A Bucket says "`limit` per `window_seconds`, with up to `burst` at once" (burst defaults to `limit`).
check() returns None when allowed (and recorded), else the seconds to wait. Time comes from the Redis server clock,
so instances with drifting clocks agree. When Redis is unavailable it falls back to the in-process sliding window
(app.ratelimit), key format unchanged, so behaviour matches what you had before this file existed.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.redis_client import key, safe

_NA = object()

_SCRIPT = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local cost = tonumber(ARGV[1])
local worst = 0
local nts = {}
for i = 1, #KEYS do
  local emission = tonumber(ARGV[2 * i])
  local tau = tonumber(ARGV[2 * i + 1])
  local tat = tonumber(redis.call('GET', KEYS[i]))
  if (not tat) or tat < now then tat = now end
  local nt = tat + emission * cost
  local wait = nt - tau - now
  if wait > worst then worst = wait end
  nts[i] = nt
end
if worst > 0 then return math.ceil(worst) end
for i = 1, #KEYS do
  redis.call('SET', KEYS[i], string.format('%.0f', nts[i]), 'PX', string.format('%.0f', math.ceil(nts[i] - now) + 1000))
end
return 0
"""


@dataclass(frozen=True, slots=True)
class Bucket:
    name: str
    limit: int
    window_seconds: int
    burst: int | None = None

    @property
    def emission_ms(self) -> float:
        return self.window_seconds * 1000.0 / self.limit

    @property
    def tau_ms(self) -> float:
        return self.emission_ms * (self.burst or self.limit)


def _fallback(subject: str, buckets: Sequence[Bucket]) -> int | None:
    from app.ratelimit import get_limiter  # lazy: ratelimit imports this module

    limiter = get_limiter()
    for b in buckets:
        retry = limiter.check(f"{b.name}:{subject}", b.limit, b.window_seconds)
        if retry is not None:
            return retry
    return None


async def check(subject: str, buckets: Sequence[Bucket], cost: int = 1) -> int | None:
    """None = allowed and recorded. Otherwise the whole seconds until the request would fit."""
    keys = [key("gcra", b.name, subject) for b in buckets]
    argv: list[float] = [cost]
    for b in buckets:
        argv.extend((b.emission_ms, b.tau_ms))
    wait_ms = await safe(lambda r: r.eval(_SCRIPT, len(keys), *keys, *argv), _NA)
    if wait_ms is _NA:
        return _fallback(subject, buckets)
    wait = int(wait_ms)  # type: ignore[arg-type]
    return None if wait <= 0 else max(1, math.ceil(wait / 1000))
