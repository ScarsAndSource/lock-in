"""
LLM client abstraction. Stub for slice 8 — the Groq layer is a later slice.
RetroService calls this; tests override it with InMemoryLLMClient.
"""
from __future__ import annotations

from typing import Protocol


class LLMError(Exception):
    """Base for all LLM-level failures."""


class LLMUnavailableError(LLMError):
    """The LLM endpoint is down or timed out."""


class LLMValidationError(LLMError):
    """The LLM returned a response that failed schema validation (after retries)."""


class LLMClient(Protocol):
    model: str

    async def complete(self, messages: list[dict], *, max_tokens: int = 512, temperature: float = 0.3) -> str:
        """Returns the raw text completion. Raises LLMError on failure."""
        ...


class GroqClient:
    """Real Groq implementation (wired in later slice). Raises LLMUnavailableError if key is missing."""

    def __init__(self, api_key: str = "", model: str = "llama-3.3-70b-versatile", timeout: float = 30.0):
        self.model = model
        self._key = api_key
        self._timeout = timeout

    async def complete(self, messages: list[dict], *, max_tokens: int = 512, temperature: float = 0.3) -> str:
        raise LLMUnavailableError("Groq client not yet wired (later slice).")
