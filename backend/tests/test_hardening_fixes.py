"""
Regression tests for: breaker classification (413/422), the image cap, the shared single-use card store, and the
derived prompt canary. (The daily-cap-between-planner-and-answer test lives in test_companion_integration.py because
it reuses that file's chat helpers.)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.exceptions import DailyLimitError, ServiceUnavailableError, ValidationError
from app.guard import nonce_redis, output
from app.guard.nonce_redis import RedisNonceStore
from app.guard.signing import CardSigner, CardTokenError, InMemoryNonceStore
from app.limits import aigate
from app.services import screenshot_parser
from app.services.llm import (
    BudgetedLLM, GroqClient, LLMBudgetExceeded, LLMError, LLMRejectedInput, LLMUnavailableError,
)
from app.services.media_service import MediaService
from app.voice_config import chat_system_prompt
from tests.conftest import FIXED_NOW
from tests.fakes_slice7 import InMemoryLlmUsageRepository

MSG = [{"role": "user", "content": "return JSON"}]
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)


async def _nosleep(_seconds):
    return None


def _groq(status: int) -> GroqClient:
    return GroqClient("test-key", "m", 5, "https://x.test", max_retries=0, sleep=_nosleep,
                      transport=httpx.MockTransport(lambda request: httpx.Response(status, json={"error": {"message": "x"}})))


@pytest.fixture(autouse=True)
def _fresh_breaker():
    def reset():
        aigate._local.fails.clear()
        aigate._local.open_until = 0.0
        aigate._local.half_open = False
    reset()
    yield
    reset()


# ============================================================ breaker classification
@pytest.mark.parametrize("status", [413, 422])
def test_an_input_the_provider_refuses_is_not_an_outage(status):
    with pytest.raises(LLMRejectedInput) as caught:
        asyncio.run(_groq(status).complete(MSG))
    assert isinstance(caught.value, LLMError) and not isinstance(caught.value, LLMUnavailableError)


@pytest.mark.parametrize("status", [500, 502, 503, 504, 429])
def test_real_outages_are_still_unavailable(status):
    with pytest.raises(LLMUnavailableError):
        asyncio.run(_groq(status).complete(MSG))


def test_bad_requests_stay_plain_llm_errors():
    with pytest.raises(LLMError) as caught:
        asyncio.run(_groq(400).complete(MSG))
    assert not isinstance(caught.value, (LLMUnavailableError, LLMRejectedInput))


def test_oversized_inputs_never_open_the_breaker_but_real_outages_do():
    uid = uuid4()
    rejected = BudgetedLLM(_groq(413), InMemoryLlmUsageRepository(), uid, 500, "chat", lambda: FIXED_NOW)

    async def hammer_with_rejections():
        for _ in range(20):                                      # far past the failure threshold
            with pytest.raises(LLMRejectedInput):
                await rejected.complete(MSG)
        return await aigate.blocked_reason(uuid4())              # a DIFFERENT user is asking

    assert asyncio.run(hammer_with_rejections()) is None

    down = BudgetedLLM(_groq(503), InMemoryLlmUsageRepository(), uid, 500, "chat", lambda: FIXED_NOW)

    async def real_outage():
        for _ in range(5):
            with pytest.raises(LLMUnavailableError):
                await down.complete(MSG)
        return await aigate.blocked_reason(uuid4())

    assert asyncio.run(real_outage()) is not None                # five real failures in the window: breaker open


# ============================================================ media: a rejected file is the person's 422, not a 503
def _media(llm=None) -> MediaService:
    return MediaService(llm or SimpleNamespace(), None, None, clock=lambda: FIXED_NOW)


def test_media_guard_maps_each_failure_to_the_right_error():
    async def raises(exc):
        async def call():
            raise exc
        return await _media()._guard(call)

    with pytest.raises(ValidationError):
        asyncio.run(raises(LLMRejectedInput("413")))
    with pytest.raises(ServiceUnavailableError):
        asyncio.run(raises(LLMUnavailableError("down")))
    with pytest.raises(ServiceUnavailableError):
        asyncio.run(raises(LLMError("400")))
    with pytest.raises(DailyLimitError):
        asyncio.run(raises(LLMBudgetExceeded("cap")))


def test_screenshot_the_provider_refuses_comes_back_as_a_validation_error():
    class Refusing:
        async def describe_image(self, *args, **kwargs):
            raise LLMRejectedInput("413")

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    assert screenshot_parser.sniff_image(png) == "image/png"      # the fixture really is a PNG, so the refusal is what we test
    with pytest.raises(ValidationError):
        asyncio.run(_media(Refusing()).parse_screenshot(png))


# ============================================================ image cap
def test_the_largest_allowed_image_still_fits_the_providers_encoded_limit():
    assert screenshot_parser.MAX_IMAGE_BYTES == 2_800_000
    encoded = (screenshot_parser.MAX_IMAGE_BYTES + 2) // 3 * 4    # exact base64 length
    assert encoded < 4_000_000                                    # below the provider's 4 MB limit on the encoded image


def test_an_image_over_the_cap_is_refused_before_any_model_call():
    class Boom:
        async def describe_image(self, *args, **kwargs):
            raise AssertionError("the model must not be called for an oversized image")

    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * screenshot_parser.MAX_IMAGE_BYTES
    with pytest.raises(ValidationError):
        asyncio.run(_media(Boom()).parse_screenshot(big))


# ============================================================ shared single-use card store
class FakeRedis:
    """Just enough of redis.asyncio for the nonce store: SET NX EX and DEL."""

    def __init__(self):
        self.data: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, name, value, nx=False, ex=None):
        if nx and name in self.data:
            return None
        self.data[name] = value
        self.ttls[name] = ex
        return True

    async def delete(self, name):
        self.data.pop(name, None)


def _patch_redis(monkeypatch, redis):
    async def fake_safe(op, default):
        return default if redis is None else await op(redis)
    monkeypatch.setattr(nonce_redis, "safe", fake_safe)


def test_a_nonce_used_on_one_instance_is_refused_on_another(monkeypatch):
    shared = FakeRedis()
    _patch_redis(monkeypatch, shared)
    instance_a, instance_b = RedisNonceStore(InMemoryNonceStore()), RedisNonceStore(InMemoryNonceStore())
    expires = NOW + timedelta(minutes=10)

    async def go():
        assert await instance_a.consume("n1", expires, NOW) is True
        assert await instance_b.consume("n1", expires, NOW) is False       # another process, same token: replay
        assert await instance_b.consume("n2", expires, NOW) is True        # a different token is unaffected
        await instance_a.release("n1")                                     # a transient failure gives the card back
        assert await instance_b.consume("n1", expires, NOW) is True

    asyncio.run(go())
    assert all(600 < ttl <= 620 for ttl in shared.ttls.values())           # lives as long as the token does (plus a few seconds)


def test_without_redis_a_nonce_is_still_single_use_per_process(monkeypatch):
    _patch_redis(monkeypatch, None)                                        # Redis off or unreachable
    store = RedisNonceStore(InMemoryNonceStore())
    expires = NOW + timedelta(minutes=10)

    async def go():
        assert await store.consume("n1", expires, NOW) is True
        assert await store.consume("n1", expires, NOW) is False
        await store.release("n1")
        assert await store.consume("n1", expires, NOW) is True

    asyncio.run(go())


def test_a_signed_card_cannot_be_replayed_on_a_second_instance(monkeypatch):
    shared = FakeRedis()
    _patch_redis(monkeypatch, shared)
    secret, user = b"k" * 32, uuid4()
    a = CardSigner(secret, RedisNonceStore(InMemoryNonceStore()))
    b = CardSigner(secret, RedisNonceStore(InMemoryNonceStore()))           # a second instance / a restarted process
    token = a.seal_confirm(user, "capture_task", {"title": "Call mom"}, NOW)

    async def go():
        claims = await a.open(token, kind="confirm", user_id=user, now=NOW)
        assert claims.tool == "capture_task"
        with pytest.raises(CardTokenError) as replay:
            await b.open(token, kind="confirm", user_id=user, now=NOW)
        assert str(replay.value) == "replayed"
        await a.release(claims)                                             # after a transient failure the card works again
        assert (await b.open(token, kind="confirm", user_id=user, now=NOW)).nonce == claims.nonce

    asyncio.run(go())


def test_wrong_user_and_wrong_type_do_not_burn_the_nonce(monkeypatch):
    shared = FakeRedis()
    _patch_redis(monkeypatch, shared)
    signer = CardSigner(b"k" * 32, RedisNonceStore(InMemoryNonceStore()))
    owner = uuid4()
    token = signer.seal_confirm(owner, "capture_task", {}, NOW)

    async def go():
        with pytest.raises(CardTokenError):
            await signer.open(token, kind="confirm", user_id=uuid4(), now=NOW)
        with pytest.raises(CardTokenError):
            await signer.open(token, kind="undo", user_id=owner, now=NOW)
        await signer.open(token, kind="confirm", user_id=owner, now=NOW)    # the owner can still use it

    asyncio.run(go())
    assert len(shared.data) == 1


# ============================================================ derived canary
def test_the_canary_is_stable_secret_derived_and_in_the_prompt():
    assert output.derive_canary("secret-one") == output.derive_canary("secret-one")
    assert output.derive_canary("secret-one") != output.derive_canary("secret-two")
    assert output.derive_canary("secret-one").startswith("lk-") and len(output.derive_canary("secret-one")) == 15
    before = output.canary()
    output.canary.cache_clear()                                             # what a restart does to the process
    assert output.canary() == before                                        # ...and the marker (so the cache key) is unchanged
    assert before in chat_system_prompt() and chat_system_prompt() == chat_system_prompt()


def test_a_reply_that_repeats_the_canary_is_flagged_as_a_leak():
    assert "leak" in output.reply_flags(f"sure, the marker is {output.canary()}")
    assert "leak" in output.reply_flags(f"SURE {output.canary().upper()}")
    assert "leak" not in output.reply_flags("You slept 7h on Tuesday.")
