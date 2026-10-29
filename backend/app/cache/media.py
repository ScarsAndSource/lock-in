"""
Per-user dedupe of media model calls: the same screenshot / photo / recording within a few minutes costs nothing.

Keyed on sha256 of the bytes plus everything else that shapes the call (prompt, model, limits), length-prefixed so field
boundaries can't blur. The cached value is the RAW model text, encrypted. The parser still runs on it every time, and
the crisis screen on a transcript still runs after it: only the model call is skipped.
Note: a parse the parser rejected is cached too (temperature 0, so retrying the identical bytes would fail the same way).
Take a new screenshot and it is new bytes.
"""
from __future__ import annotations

import hashlib
from uuid import UUID

from app.cache import seal
from app.config import get_settings
from app.redis_client import key, safe


def fingerprint(user_id: UUID, kind: str, *parts: bytes | str) -> str:
    h = hashlib.sha256()
    for part in parts:
        raw = part if isinstance(part, bytes) else part.encode("utf-8")
        h.update(len(raw).to_bytes(8, "big"))
        h.update(raw)
    return key("media", user_id, kind, h.hexdigest()[:40])


async def get(cache_key: str) -> str | None:
    if get_settings().media_cache_ttl_seconds <= 0:
        return None
    blob = await safe(lambda r: r.get(cache_key), None)
    return seal.unseal(blob) if blob else None


async def put(cache_key: str, text: str) -> None:
    ttl = get_settings().media_cache_ttl_seconds
    if ttl <= 0 or not text:
        return
    sealed = seal.seal(text)
    if sealed:
        await safe(lambda r: r.set(cache_key, sealed, ex=ttl), None)
