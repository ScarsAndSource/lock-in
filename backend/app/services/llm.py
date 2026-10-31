"""
LLM layer.
GroqClient real OpenAI-compatible chat call over httpx, JSON mode on (every prompt here returns JSON).
BudgetedLLM wraps any client. Media calls (audio, images) are deduplicated first: the same bytes within a few minutes
return the cached raw text for free. Every real call then passes, in order: (1) the kill-switch/breaker
(limits/aigate.py), (2) the chat turn if the request is inside a turn_scope (limits/turn.py), (3) the weighted Redis
budget (limits/budget.py: units + tokens per day), (4) the per-user DAILY call cap via llm_usage.
Failure model: LLMUnavailableError (down, timeout, not configured, auth, switched off, breaker open) and LLMError
(malformed reply) both mean "use the deterministic fallback".
LLMBudgetExceeded is an LLMError, so narrators fall back on it too; chat turns it into a 429.
Privacy: prompts, completions and the key are never logged.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

import httpx

from app.cache import media as media_cache
from app.dates import Clock, utc_now
from app.limits import aigate, budget, ceiling, slots
from app.limits.turn import current_turn
from app.repositories.llm_usage_repository import LlmUsageRepository

logger = logging.getLogger("lockin.llm")

_RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_MAX_BACKOFF_SECONDS = 5.0


class LLMError(Exception):
    """Base for all LLM-level failures."""


class LLMUnavailableError(LLMError):
    """The LLM endpoint is down, timed out, rejected us, isn't configured, or has been switched off."""


class LLMValidationError(LLMError):
    """The LLM returned a response that failed schema validation (after retries)."""


class LLMBudgetExceeded(LLMError):
    """The user's daily AI allowance (calls, weighted units or tokens) is used up."""


class LLMRejectedInput(LLMError):
    """The provider refused THIS input (HTTP 413 too large, 422 unprocessable). The provider is fine: it is not an
    outage, so it never counts toward the circuit breaker, and media callers turn it into a 422 for the person."""


class LLMClient(Protocol):
    model: str

    async def complete(self, messages: list[dict], *, max_tokens: int = 512, temperature: float = 0.3) -> str:
        """Returns the raw text completion. Raises LLMError on failure."""
        ...


class MediaLLM(LLMClient, Protocol):
    """Speech-to-text and image reading, for voice check-in and screenshot screen time."""

    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str: ...

    async def describe_image(self, image: bytes, media_type: str, prompt: str, *, max_tokens: int = 400) -> str: ...


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
        transcribe_model: str = "whisper-large-v3-turbo",
        vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct",
    ):
        self.model = model
        self.transcribe_model = transcribe_model
        self.vision_model = vision_model
        self.last_tokens = 0
        self._key = api_key
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")
        self._max_retries = max(0, max_retries)
        self._json_mode = json_mode
        self._transport = transport
        self._sleep = sleep or asyncio.sleep

    async def complete(self, messages: list[dict], *, max_tokens: int = 512, temperature: float = 0.3) -> str:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        return self._parse(await self._send("/chat/completions", json_body=payload))

    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        """Speech to text. Returns the stripped transcript, which may be empty (silence)."""
        self.last_tokens = 0  # audio calls report no token usage; don't let the previous call's number leak in
        resp = await self._send(
            "/audio/transcriptions",
            data={"model": self.transcribe_model, "response_format": "json", "temperature": "0"},
            files={"file": (filename, audio, content_type)},
        )
        try:
            text = resp.json()["text"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError("Groq returned an unexpected transcription shape.") from exc
        if not isinstance(text, str):
            raise LLMError("Groq returned an unexpected transcription shape.")
        return text.strip()

    async def describe_image(self, image: bytes, media_type: str, prompt: str, *, max_tokens: int = 400) -> str:
        """One vision call. No JSON mode here (vision models don't all support it): the prompt asks for JSON."""
        data_url = f"data:{media_type};base64,{base64.b64encode(image).decode('ascii')}"
        payload = {
            "model": self.vision_model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
        }
        return self._parse(await self._send("/chat/completions", json_body=payload))

    async def _send(self, path: str, *, json_body: dict | None = None, data: dict | None = None, files=None) -> httpx.Response:
        """POST with the retry/backoff and error mapping every Groq call shares. Returns only a 200 response."""
        if not self._key:
            raise LLMUnavailableError("GROQ_API_KEY is not set.")
        headers = {"Authorization": f"Bearer {self._key}"}  # httpx sets Content-Type (json or multipart boundary)
        url = f"{self._base_url}{path}"
        reason = "unknown"
        for attempt in range(self._max_retries + 1):
            wait: float | None = None
            try:
                async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                    resp = await client.post(url, json=json_body, data=data, files=files, headers=headers)
            except httpx.TimeoutException:
                reason = "timeout"
            except httpx.HTTPError:
                reason = "network error"
            else:
                if resp.status_code == 200:
                    return resp
                if resp.status_code in (401, 403):
                    logger.error("Groq auth failed (HTTP %s) -- check GROQ_API_KEY", resp.status_code)
                    raise LLMUnavailableError(f"Groq rejected our credentials (HTTP {resp.status_code}).")
                if resp.status_code == 400:
                    raise LLMError("Groq rejected the request (HTTP 400).")  # e.g. JSON mode failed, bad audio/image
                if resp.status_code in (413, 422):
                    # One person's oversized or unreadable input. Must NOT be LLMUnavailableError: five of these in a
                    # row from a single user would open the breaker and switch AI off for everyone.
                    raise LLMRejectedInput(f"Groq rejected this input (HTTP {resp.status_code}).")
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
    Gate in front of every model call, in this order:
      0. media only: the same bytes seen in the last few minutes return the cached text (free, no gate, no cap slot)
      1. kill-switch / breaker (aigate): refused calls raise LLMUnavailableError BEFORE anything is spent or charged,
         so a paused AI costs the person no quota and no daily-cap slot
      2. the chat turn, if this request is inside a turn_scope: takes the per-user lock and spends ONE rate slot,
         once per request however many model calls the turn makes (can raise ConflictError / RateLimitedError)
      3. weighted Redis budget (budget.py): units reserved atomically, tokens checked against the day's total
      4. per-user daily call cap. consume() is an atomic upsert-increment; if the day's total goes over the cap the call
         is refunded and LLMBudgetExceeded is raised.
    A call that failed because Groq was unavailable is refunded everywhere, so outages never burn someone's allowance,
    and it is reported to the breaker.
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

    async def _metered(self, call: Callable[[], Awaitable[str]], weight: int = budget.WEIGHT_TEXT) -> str:
        reason = await aigate.blocked_reason(self._user_id)
        if reason is not None:
            raise LLMUnavailableError(f"AI is switched off right now ({reason}).")
        # A bounded number of model calls in flight per instance (they pin DB connections while they wait). Refused
        # BEFORE anything is charged and outside the breaker's try, so being busy never counts as the provider failing.
        try:
            async with slots.ai_slot():
                return await self._metered_in_slot(call, weight)
        except slots.SlotsBusy as exc:
            raise LLMUnavailableError("AI is busy right now.") from exc

    async def _metered_in_slot(self, call: Callable[[], Awaitable[str]], weight: int) -> str:
        turn = current_turn.get()
        if turn is not None:
            await turn.charge()

        day = self._clock().astimezone(timezone.utc).date()
        over = await budget.reserve(self._user_id, day, weight)
        if over is not None:
            raise LLMBudgetExceeded(f"Daily AI {over} limit reached.")

        total = await self._usage.consume(self._user_id, day, self._feature)
        if total > self._cap:
            await self._usage.release(self._user_id, day, self._feature)
            await budget.refund(self._user_id, day, weight)
            raise LLMBudgetExceeded("Daily AI limit reached.")
        try:
            text = await call()
        except LLMUnavailableError:
            await self._usage.release(self._user_id, day, self._feature)
            await budget.refund(self._user_id, day, weight)
            await aigate.record_failure()
            raise
        aigate.record_success()
        tokens = getattr(self._inner, "last_tokens", 0)
        if tokens:
            await self._usage.add_tokens(self._user_id, day, self._feature, tokens)
            await budget.add_tokens(self._user_id, day, tokens)
        await ceiling.note(calls=1, tokens=tokens or 0)       # the all-users daily ceiling (off unless configured)
        return text

    async def complete(self, messages: list[dict], *, max_tokens: int = 512, temperature: float = 0.3) -> str:
        return await self._metered(
            lambda: self._inner.complete(messages, max_tokens=max_tokens, temperature=temperature),
            budget.WEIGHT_TEXT,
        )

    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        ck = media_cache.fingerprint(
            self._user_id, "stt", audio, filename, content_type, getattr(self._inner, "transcribe_model", ""),
        )
        hit = await media_cache.get(ck)
        if hit is not None:
            return hit
        text = await self._metered(
            lambda: self._inner.transcribe(audio, filename, content_type), budget.WEIGHT_AUDIO,
        )
        await media_cache.put(ck, text)
        return text

    async def describe_image(self, image: bytes, media_type: str, prompt: str, *, max_tokens: int = 400) -> str:
        ck = media_cache.fingerprint(
            self._user_id, "img", image, media_type, prompt, str(max_tokens), getattr(self._inner, "vision_model", ""),
        )
        hit = await media_cache.get(ck)
        if hit is not None:
            return hit
        text = await self._metered(
            lambda: self._inner.describe_image(image, media_type, prompt, max_tokens=max_tokens),
            budget.WEIGHT_VISION,
        )
        await media_cache.put(ck, text)
        return text


def scoped(llm: LLMClient, feature: str) -> LLMClient:
    """Label usage by feature when the client supports it (test fakes pass through untouched)."""
    return llm.for_feature(feature) if hasattr(llm, "for_feature") else llm
