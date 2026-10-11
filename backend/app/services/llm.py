"""
LLM layer.
GroqClient real OpenAI-compatible chat call over httpx, JSON mode on (every prompt here returns JSON).
BudgetedLLM wraps any client and enforces the per-user DAILY call cap via llm_usage.
Failure model: LLMUnavailableError (down, timeout, not configured, auth) and LLMError (malformed reply)
both mean "use the deterministic fallback".
LLMBudgetExceeded is an LLMError, so narrators fall back on it too; chat turns it into a 429.
Privacy: prompts, completions and the key are never logged.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

import httpx

from app.dates import Clock, utc_now
from app.repositories.llm_usage_repository import LlmUsageRepository

logger = logging.getLogger("lockin.llm")

_RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_MAX_BACKOFF_SECONDS = 5.0


class LLMError(Exception):
    """Base for all LLM-level failures."""


class LLMUnavailableError(LLMError):
    """The LLM endpoint is down, timed out, rejected us, or isn't configured."""


class LLMValidationError(LLMError):
    """The LLM returned a response that failed schema validation (after retries)."""


class LLMBudgetExceeded(LLMError):
    """The user's daily AI-call cap is used up."""


class LLMClient(Protocol):
    model: str

    async def complete(self, messages: list[dict], *, max_tokens: int = 512, temperature: float = 0.3) -> str:
        """Returns the raw text completion. Raises LLMError on failure."""
        ...


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return float(resp.headers.get("retry-after", ""))
    except ValueError:
        return None


class GroqClient:
    def __init__(
        self,
        api_key: str = "",
        model: str = "llama-3.3-70b-versatile",
        timeout: float = 20.0,
        base_url: str = "https://api.groq.com/openai/v1",
        *,
        max_retries: int = 1,
        json_mode: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ):
        self.model = model
        self.last_tokens = 0
        self._key = api_key
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")
        self._max_retries = max(0, max_retries)
        self._json_mode = json_mode
        self._transport = transport
        self._sleep = sleep or asyncio.sleep

    async def complete(self, messages: list[dict], *, max_tokens: int = 512, temperature: float = 0.3) -> str:
        if not self._key:
            raise LLMUnavailableError("GROQ_API_KEY is not set.")
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        url = f"{self._base_url}/chat/completions"
        reason = "unknown"
        for attempt in range(self._max_retries + 1):
            wait: float | None = None
            try:
                async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                    resp = await client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException:
                reason = "timeout"
            except httpx.HTTPError:
                reason = "network error"
            else:
                if resp.status_code == 200:
                    return self._parse(resp)
                if resp.status_code in (401, 403):
                    logger.error("Groq auth failed (HTTP %s) -- check GROQ_API_KEY", resp.status_code)
                    raise LLMUnavailableError(f"Groq rejected our credentials (HTTP {resp.status_code}).")
                if resp.status_code == 400:
                    raise LLMError("Groq rejected the request (HTTP 400).")  # e.g. JSON mode failed
                if resp.status_code not in _RETRYABLE_STATUS:
                    raise LLMUnavailableError(f"Groq rejected the request (HTTP {resp.status_code}).")
                reason = f"HTTP {resp.status_code}"
                wait = _retry_after(resp)
            if attempt < self._max_retries:
                logger.warning("Groq call failed (%s); retrying", reason)
                delay = wait if wait is not None else 0.5 * (2 ** attempt)
                await self._sleep(min(delay, _MAX_BACKOFF_SECONDS))
        raise LLMUnavailableError(f"Groq unavailable ({reason}).")

    def _parse(self, resp: httpx.Response) -> str:
        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("Groq returned an unexpected response shape.") from exc
        if not isinstance(text, str) or not text.strip():
            raise LLMError("Groq returned an empty completion.")
        usage = data.get("usage")
        self.last_tokens = int(usage.get("total_tokens", 0)) if isinstance(usage, dict) else 0
        return text


def seconds_until_reset(now: datetime) -> int:
    """Seconds until the next 00:00 UTC (when the daily cap resets)."""
    now = now.astimezone(timezone.utc)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((nxt - now).total_seconds()))


class BudgetedLLM:
    """
    Per-user daily cap. consume() is an atomic upsert-increment; if the day's total goes
    over the cap the call is refunded and LLMBudgetExceeded is raised.
    A call that failed because Groq was unavailable is refunded too, so outages never burn
    someone's allowance.
    """

    def __init__(
        self,
        inner: LLMClient,
        usage: LlmUsageRepository,
        user_id: UUID,
        cap: int,
        feature: str = "chat",
        clock: Clock = utc_now,
    ):
        self._inner, self._usage, self._user_id = inner, usage, user_id
        self._cap, self._feature, self._clock = cap, feature, clock

    @property
    def model(self) -> str:
        return self._inner.model

    def for_feature(self, feature: str) -> "BudgetedLLM":
        return BudgetedLLM(self._inner, self._usage, self._user_id, self._cap, feature, self._clock)

    async def complete(self, messages: list[dict], *, max_tokens: int = 512, temperature: float = 0.3) -> str:
        day = self._clock().astimezone(timezone.utc).date()
        total = await self._usage.consume(self._user_id, day, self._feature)
        if total > self._cap:
            await self._usage.release(self._user_id, day, self._feature)
            raise LLMBudgetExceeded("Daily AI limit reached.")
        try:
            text = await self._inner.complete(messages, max_tokens=max_tokens, temperature=temperature)
        except LLMUnavailableError:
            await self._usage.release(self._user_id, day, self._feature)
            raise
        tokens = getattr(self._inner, "last_tokens", 0)
        if tokens:
            await self._usage.add_tokens(self._user_id, day, self._feature, tokens)
        return text


def scoped(llm: LLMClient, feature: str) -> LLMClient:
    """Label usage by feature when the client supports it (test fakes pass through untouched)."""
    return llm.for_feature(feature) if hasattr(llm, "for_feature") else llm
