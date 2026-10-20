import httpx
import pytest

from app.config import Settings
from app.services.llm import GroqClient, LLMUnavailableError


def _settings() -> Settings:
    return Settings(database_url="postgresql+asyncpg://x", field_encryption_key="k", supabase_jwt_secret="s")


def test_groq_defaults_fail_fast():
    s = _settings()
    assert s.groq_timeout_seconds <= 10
    assert s.groq_max_retries == 0


@pytest.mark.asyncio
async def test_zero_retries_is_a_single_attempt():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500)

    client = GroqClient("key", max_retries=0, transport=httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError):
        await client.complete([{"role": "user", "content": "hi"}])
    assert len(calls) == 1
