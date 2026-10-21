"""
Signed action tokens for pushes you can act on without opening the app.

The service worker holds no session, so each actionable push carries ONE token. It is:
  * signed (HMAC-SHA256) so it cannot be forged or edited -- the user id, push id, kind, args and the list of
    actions it authorises are all inside the signature;
  * short-lived (`exp`), because a lock-screen button that still works next week is a liability;
  * single-use: `push_id` is the primary key of the companion_pushes ledger row, and acting flips acted_at
    atomically. A replayed or double-tapped token finds the row already acted and does nothing.
The token authorises only the actions listed in `acts` (plus "open"), never anything else.
PURE: no DB, no clock, no network. Everything arrives as an argument.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

MAX_TOKEN_CHARS = 1400
_CTX = b"lockin/push-action/v1"


class ActionTokenError(Exception):
    """code: malformed | bad_signature | expired"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ActionClaims:
    user_id: UUID
    push_id: UUID
    kind: str
    args: dict
    allowed: tuple[str, ...]
    expires_at: datetime


def derive_secret(explicit: str, field_encryption_key: str) -> bytes:
    """A dedicated PUSH_ACTION_SECRET wins; otherwise derive one from the field-encryption key (domain-separated)."""
    if explicit:
        return explicit.encode()
    return hmac.new(field_encryption_key.encode(), _CTX, hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: bytes, body: str) -> str:
    return _b64(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())


def mint(
    secret: bytes, *, user_id: UUID, push_id: UUID, kind: str, args: dict, allowed: tuple[str, ...],
    expires_at: datetime,
) -> str:
    payload = {
        "u": str(user_id), "p": str(push_id), "k": kind, "a": args, "w": list(allowed),
        "e": int(expires_at.astimezone(timezone.utc).timestamp()),
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    token = f"{body}.{_sign(secret, body)}"
    if len(token) > MAX_TOKEN_CHARS:
        raise ValueError("action token too large")  # a programming error, never user input
    return token


def verify(secret: bytes, token: str, now: datetime) -> ActionClaims:
    if not isinstance(token, str) or len(token) > MAX_TOKEN_CHARS or token.count(".") != 1:
        raise ActionTokenError("malformed")
    body, sig = token.split(".")
    try:
        body.encode("ascii")
        sig.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ActionTokenError("malformed") from exc
    if not hmac.compare_digest(_sign(secret, body), sig):  # constant time; checked BEFORE the body is parsed
        raise ActionTokenError("bad_signature")
    try:
        data = json.loads(_unb64(body))
        claims = ActionClaims(
            user_id=UUID(data["u"]), push_id=UUID(data["p"]), kind=str(data["k"]),
            args={str(k): str(v) for k, v in dict(data["a"]).items()},
            allowed=tuple(str(x) for x in data["w"]),
            expires_at=datetime.fromtimestamp(int(data["e"]), tz=timezone.utc),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ActionTokenError("malformed") from exc
    if now >= claims.expires_at:
        raise ActionTokenError("expired")
    return claims
