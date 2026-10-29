"""
Per-user cache of the chat evidence pack (the ~7 DB queries in ChatService._gather).

Stored as  <data version>|<encrypted json>  under one key, and read together with the live version in ONE round trip
(MGET). A hit needs the stored version to equal the current one. The version is read BEFORE building, so a write that
lands while the pack is being built leaves it stamped with the old version and it is simply never reused.

Bypassed (no read, no write) when the request has already written (data_version.mark_dirty), when the TTL is 0, and
when Redis is unavailable.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from uuid import UUID

from app.cache import data_version, seal
from app.config import get_settings
from app.redis_client import key, safe


async def get_or_build(user_id: UUID, builder: Callable[[], Awaitable[dict]]) -> dict:
    ttl = get_settings().facts_cache_ttl_seconds
    if ttl <= 0 or data_version.is_dirty():
        return await builder()

    fkey = key("facts", user_id)
    got = await safe(lambda r: r.mget(data_version.key_for(user_id), fkey), None)
    if got is None:                      # Redis off or unreachable
        return await builder()

    version = got[0] or b"0"
    blob = got[1]
    if blob:
        head, _, payload = blob.partition(b"|")
        if head == version:
            text = seal.unseal(payload)
            if text is not None:
                try:
                    return json.loads(text)
                except ValueError:
                    pass

    facts = await builder()
    try:
        text = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return facts                     # not JSON-clean: serve it, don't cache it
    sealed = seal.seal(text)
    if sealed:
        await safe(lambda r: r.set(fkey, version + b"|" + sealed, ex=ttl), None)
    return facts
