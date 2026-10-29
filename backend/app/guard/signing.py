"""
Signed action cards: pending cards and undo chips carry an HMAC-signed token instead of client-editable JSON.
Signed (domain-separated key), bound to the user id, typed (confirm vs undo), short-lived, and single-use (nonce).
Single-use is enforced by a NonceStore: the default is in-process; the Redis layer swaps in a shared one with the same
two methods. PURE apart from the NonceStore: secret, clock and ids arrive as arguments.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

MAX_TOKEN_CHARS = 8000
DEFAULT_TTL = timedelta(minutes=10)
_CTX = b"lockin/chat-card/v1"


class CardTokenError(Exception):
    """code: malformed | bad_signature | expired | wrong_type | wrong_user | replayed"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class NonceStore(Protocol):
    def consume(self, nonce: str, expires_at: datetime, now: datetime) -> bool: ...   # True only the first time
    def release(self, nonce: str) -> None: ...


class InMemoryNonceStore:
    """Process-local and bounded. Expired entries are dropped; a hard cap stops a flood from growing it."""

    def __init__(self, max_entries: int = 50_000):
        self._seen: dict[str, datetime] = {}
        self._max = max_entries
        self._lock = threading.Lock()

    def consume(self, nonce: str, expires_at: datetime, now: datetime) -> bool:
        with self._lock:
            if len(self._seen) >= self._max // 2:
                self._seen = {n: e for n, e in self._seen.items() if e > now}
            if nonce in self._seen and self._seen[nonce] > now:
                return False
            if len(self._seen) >= self._max:
                return False            # fail closed under a flood
            self._seen[nonce] = expires_at
            return True

    def release(self, nonce: str) -> None:
        with self._lock:
            self._seen.pop(nonce, None)


@dataclass(frozen=True, slots=True)
class CardClaims:
    kind: str                # "confirm" | "undo"
    user_id: UUID
    tool: str | None         # confirm only
    payload: dict
    nonce: str
    expires_at: datetime


def derive_secret(field_encryption_key: str, explicit: str = "") -> bytes:
    """Derived under its OWN context label, so it is never the same key as the push-action secret."""
    if explicit:
        return explicit.encode()
    return hmac.new(field_encryption_key.encode(), _CTX, hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: bytes, body: str) -> str:
    return _b64(hmac.new(secret, _CTX + b"." + body.encode("ascii"), hashlib.sha256).digest())


class CardSigner:
    def __init__(self, secret: bytes, nonces: NonceStore | None = None, ttl: timedelta = DEFAULT_TTL):
        if not secret:
            raise ValueError("CardSigner needs a non-empty secret.")
        self._secret, self._nonces, self._ttl = secret, nonces or InMemoryNonceStore(), ttl

    def _mint(self, kind: str, user_id: UUID, tool: str | None, payload: dict, now: datetime) -> str:
        expires = now + self._ttl
        body_obj = {
            "v": 1, "t": kind, "u": str(user_id), "k": tool, "a": payload,
            "e": int(expires.astimezone(timezone.utc).timestamp()), "n": secrets.token_urlsafe(12),
        }
        body = _b64(json.dumps(body_obj, separators=(",", ":"), sort_keys=True).encode())
        token = f"{body}.{_sign(self._secret, body)}"
        if len(token) > MAX_TOKEN_CHARS:
            raise ValueError("card token too large")
        return token

    def seal_confirm(self, user_id: UUID, tool: str, args: dict, now: datetime) -> str:
        return self._mint("confirm", user_id, tool, args, now)

    def seal_undo(self, user_id: UUID, payload: dict, now: datetime) -> str:
        return self._mint("undo", user_id, None, payload, now)

    def verify(self, token: str, now: datetime) -> CardClaims:
        """Signature, shape and expiry only. Does not consume the nonce."""
        if not isinstance(token, str) or len(token) > MAX_TOKEN_CHARS or token.count(".") != 1:
            raise CardTokenError("malformed")
        body, sig = token.split(".")
        try:
            body.encode("ascii")
            sig.encode("ascii")
        except UnicodeEncodeError as exc:
            raise CardTokenError("malformed") from exc
        if not hmac.compare_digest(_sign(self._secret, body), sig):      # constant time, BEFORE the body is parsed
            raise CardTokenError("bad_signature")
        try:
            data = json.loads(_unb64(body))
            claims = CardClaims(
                kind=str(data["t"]), user_id=UUID(data["u"]), tool=None if data["k"] is None else str(data["k"]),
                payload=dict(data["a"]), nonce=str(data["n"]),
                expires_at=datetime.fromtimestamp(int(data["e"]), tz=timezone.utc),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise CardTokenError("malformed") from exc
        if now >= claims.expires_at:
            raise CardTokenError("expired")
        return claims

    def open(self, token: str, *, kind: str, user_id: UUID, now: datetime) -> CardClaims:
        """Verify, check type and owner, then consume the nonce. If applying fails transiently, call release(claims)."""
        claims = self.verify(token, now)
        if claims.kind != kind:
            raise CardTokenError("wrong_type")
        if claims.user_id != user_id:
            raise CardTokenError("wrong_user")
        if not self._nonces.consume(claims.nonce, claims.expires_at, now):
            raise CardTokenError("replayed")
        return claims

    def release(self, claims: CardClaims) -> None:
        self._nonces.release(claims.nonce)
