"""
A chat "turn": the unit that rate limits and the in-flight lock are charged against.

The old code charged a rate-limit slot every time a service called before_model(), and the agent flow calls it twice
(planner, then the answer), so a plain "log gym" message burned two of your six slots a minute. Here the router opens
turn_scope() around the whole request; the FIRST model call inside it (BudgetedLLM._metered) calls charge(), which
takes the per-user lock and spends ONE slot from the chat buckets. Every later model call in the same request is free.

What that gives you:
  * the crisis/support path and the "nothing logged yet" reply never call the model, so they never charge, never take
    the lock and are never limited
  * a double-tapped Send gets a quick 409 instead of a second model call
  * a refused request spends nothing and holds nothing (the lock is released before the 429 is raised)
  * AI switched off by the kill-switch/breaker is checked BEFORE charge(), so a paused AI never costs the person quota
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from uuid import UUID

from app.config import Settings
from app.exceptions import ConflictError, RateLimitedError
from app.limits import gcra, lock, strikes

BUSY_MESSAGE = "Still working on your last message. Give me a second."

current_turn: ContextVar["TurnGate | None"] = ContextVar("lockin_current_turn", default=None)


class TurnGate:
    def __init__(self, user_id: UUID, settings: Settings):
        self._user = str(user_id)
        self._settings = settings
        self._charged = False
        self._token: str | None = None
        self._mutex = asyncio.Lock()

    async def charge(self) -> None:
        async with self._mutex:
            if self._charged:
                return
            s = self._settings
            if s.chat_inflight_lock_seconds > 0:
                token = await lock.acquire("chat", self._user, s.chat_inflight_lock_seconds)
                if token is None:
                    raise ConflictError(BUSY_MESSAGE)
                self._token = token
            if s.rate_limit_enabled:
                scale = await strikes.cap_scale(self._user)          # 0.5 while the person's AI limits are halved
                retry_after = await gcra.check(self._user, [
                    gcra.Bucket("chat_min", strikes.scaled(s.rate_limit_chat_per_minute, scale), 60),
                    gcra.Bucket("chat_hour", strikes.scaled(s.rate_limit_chat_per_hour, scale), 3600),
                ])
                if retry_after is not None:
                    await self._release_lock()
                    await strikes.note_limited(self._user, "chat")
                    raise RateLimitedError(retry_after)
            self._charged = True

    async def _release_lock(self) -> None:
        token, self._token = self._token, None
        if token is not None:
            await lock.release("chat", self._user, token)

    async def release(self) -> None:
        await self._release_lock()


@asynccontextmanager
async def turn_scope(user_id: UUID, settings: Settings) -> AsyncIterator[TurnGate]:
    """Wrap one chat request. The lock is always released, success or failure."""
    gate = TurnGate(user_id, settings)
    token = current_turn.set(gate)
    try:
        yield gate
    finally:
        current_turn.reset(token)
        await gate.release()
