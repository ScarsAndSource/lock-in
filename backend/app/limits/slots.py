"""
Model calls in flight per instance (settings.ai_max_concurrent, default 6).

Why: a request holds its database connection while the model answers. If the provider slows down, every in-flight chat
holds one, and the pool (default 30) runs dry for everyone, including the plain tracker screens. Capping concurrent model
calls bounds how many connections the AI can pin, and waiting is itself bounded (ai_slot_wait_seconds, default 3): past
that the call is refused with SlotsBusy and BudgetedLLM turns it into LLMUnavailableError, so the feature takes the same
deterministic fallback as an outage. A refusal here happens BEFORE anything is charged, and is never counted by the
circuit breaker. The crisis path never calls a model, so it never waits for a slot.

One semaphore per event loop (a semaphore is bound to the loop it first waits on; tests and reload create several).
"""
from __future__ import annotations

import asyncio
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.config import get_settings


class SlotsBusy(Exception):
    """No model slot freed up within ai_slot_wait_seconds."""


_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, tuple[int, asyncio.Semaphore]]" = weakref.WeakKeyDictionary()


def _semaphore(size: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    held = _semaphores.get(loop)
    if held is None or held[0] != size:
        held = (size, asyncio.Semaphore(size))
        _semaphores[loop] = held
    return held[1]


@asynccontextmanager
async def ai_slot() -> AsyncIterator[None]:
    s = get_settings()
    if s.ai_max_concurrent <= 0:
        yield
        return
    sem = _semaphore(s.ai_max_concurrent)
    try:
        await asyncio.wait_for(sem.acquire(), timeout=s.ai_slot_wait_seconds)
    except asyncio.TimeoutError as exc:
        raise SlotsBusy() from exc
    try:
        yield
    finally:
        sem.release()
