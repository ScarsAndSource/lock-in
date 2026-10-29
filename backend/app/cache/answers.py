"""
Cache of VALIDATED chat answers.

The key is a hash of the exact message list sent to the model (+ model name), so it covers the facts, the tone, the
system prompt, the history and the question: change any of them and it is a different key. There is no staleness to
manage and no way to serve an answer built for different facts.

Only validated answers are stored (put it after every output check), and only the answer branch of ChatService.reply
uses it. Never used for crisis replies, planner/action output or anything across users (the user id is in the key).
Realistic hit rate: starter prompts at the top of a new thread, and identical stateless calls.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from app.cache import seal
from app.config import get_settings
from app.redis_client import key, safe


@dataclass(frozen=True, slots=True)
class CachedAnswer:
    observation: str
    next_step: str | None
    cited_days: list[str]


def _key(user_id: UUID, messages: list[dict], model: str) -> str:
    raw = json.dumps([model, messages], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return key("ans", user_id, hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40])


async def get(user_id: UUID, messages: list[dict], model: str) -> CachedAnswer | None:
    if get_settings().answer_cache_ttl_seconds <= 0:
        return None
    k = _key(user_id, messages, model)
    blob = await safe(lambda r: r.get(k), None)
    if not blob:
        return None
    text = seal.unseal(blob)
    if text is None:
        return None
    try:
        data = json.loads(text)
        observation, next_step, days = data["o"], data["n"], data["c"]
        if not isinstance(observation, str) or not isinstance(days, list):
            return None
        return CachedAnswer(observation, next_step if isinstance(next_step, str) else None, [str(d) for d in days])
    except (ValueError, KeyError, TypeError):
        return None


async def put(user_id: UUID, messages: list[dict], model: str, narration) -> None:
    ttl = get_settings().answer_cache_ttl_seconds
    if ttl <= 0:
        return
    payload = json.dumps(
        {"o": narration.observation, "n": narration.next_step, "c": [str(d) for d in narration.cited_days]},
        ensure_ascii=False,
    )
    sealed = seal.seal(payload)
    if sealed:
        k = _key(user_id, messages, model)
        await safe(lambda r: r.set(k, sealed, ex=ttl), None)
