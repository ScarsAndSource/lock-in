"""
Idempotency-Key for POST /chat/messages.

A phone on flaky signal retries; a person double-taps; the service worker replays. Without this each retry is another
model call AND another stored message pair. With it the first request owns the key, and any repeat gets the SAME reply
back (no model call, no duplicate rows, same thread id).

  begin()     -> None to proceed (this request now owns the key) | the stored reply JSON to return instead
                 raises ConflictError if the first attempt is still running,
                 ValidationError if the key is reused for a DIFFERENT message
  complete()  -> store the reply (ENCRYPTED with the same Fernet keys as stored chats; Redis never sees plaintext)
  abort()     -> drop the key after a failure (429, 409, 5xx...) so the client's retry runs normally

No header, or Redis unavailable => no dedupe, everything works exactly as before.
"""
from __future__ import annotations

import hashlib
import re
from uuid import UUID

from app.config import Settings
from app.exceptions import ConflictError, ValidationError
from app.redis_client import key, safe
from app.security import FieldEncryptor

_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")
_NA = object()


class Idempotency:
    def __init__(self, user_id: UUID, raw_key: str | None, fingerprint: str, settings: Settings):
        self._user = str(user_id)
        self._raw = raw_key.strip() if raw_key else None
        self._fp = fingerprint.encode("ascii")
        self._settings = settings
        self._rkey: str | None = None   # set only while THIS request owns the slot
        self._pending_ttl = max(60, settings.chat_inflight_lock_seconds + 20)

    def _encryptor(self) -> FieldEncryptor:
        return FieldEncryptor(self._settings.field_encryption_key, self._settings.old_encryption_keys)

    async def begin(self) -> str | None:
        if not self._raw:
            return None
        if not _KEY_RE.match(self._raw):
            raise ValidationError("Idempotency-Key must be 8-64 characters: letters, digits, - or _.")
        k = key("idem", self._user, hashlib.sha256(self._raw.encode()).hexdigest()[:32])

        got = await safe(lambda r: r.set(k, b"P:" + self._fp, nx=True, ex=self._pending_ttl), _NA)
        if got is _NA:
            return None                      # Redis off: no dedupe
        if got:
            self._rkey = k                   # we own it
            return None

        cur = await safe(lambda r: r.get(k), None)
        if not cur:
            return None                      # expired between the two calls: just run it
        parts = cur.split(b":", 2)
        state = parts[0]
        stored_fp = parts[1] if len(parts) > 1 else b""
        if stored_fp != self._fp:
            raise ValidationError("That Idempotency-Key was already used for a different message.")
        if state == b"P":
            raise ConflictError("That message is still being processed.")
        if state == b"D" and len(parts) > 2:
            try:
                text = self._encryptor().decrypt(parts[2])
            except ValueError:
                return None                  # unreadable (key rotated): run it again
            return text
        return None

    async def complete(self, payload_json: str) -> None:
        if self._rkey is None:
            return
        k, self._rkey = self._rkey, None
        cipher = self._encryptor().encrypt(payload_json) or b""
        await safe(
            lambda r: r.set(k, b"D:" + self._fp + b":" + cipher, ex=self._settings.idempotency_ttl_seconds), None,
        )

    async def abort(self) -> None:
        if self._rkey is None:
            return
        k, self._rkey = self._rkey, None
        await safe(lambda r: r.delete(k), None)
