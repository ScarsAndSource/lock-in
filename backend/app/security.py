"""
Two unrelated responsibilities live here, both security-critical enough to
keep in one small, heavily-tested module rather than scattered:

1. Verifying the Supabase-issued JWT on every request (get_current_user_id).
2. Field-level encryption for the most sensitive columns in the schema
   (urge_logs.trigger_context/note, daily_checkins.journal_encrypted) —
   see SPEC.md section 6 on why these specific fields don't rely on RLS
   alone.
"""
from __future__ import annotations

from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import Settings, get_settings

_bearer_scheme = HTTPBearer(auto_error=False)


def decode_supabase_jwt(token: str, settings: Settings) -> dict:
    """
    Decode and verify a Supabase-issued JWT.

    Raises jose.JWTError (or a subclass) on any failure — expired,
    malformed, wrong audience, or bad signature. Callers must not swallow
    this silently; get_current_user_id below turns it into a 401.
    """
    return jwt.decode(
        token,
        settings.supabase_jwt_secret,
        algorithms=["HS256"],
        audience=settings.supabase_jwt_audience,
    )


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> UUID:
    """
    FastAPI dependency: extracts and verifies the caller's identity.

    Every route that touches user data must depend on this — there is no
    "trusted" internal caller in this API, since even the friend-group
    v1 uses the exact same code path a public launch would (per SPEC.md's
    explicit note on this).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    try:
        payload = decode_supabase_jwt(credentials.credentials, settings)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        ) from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim.",
        )

    try:
        return UUID(subject)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid user id.",
        ) from exc


class FieldEncryptor:
    """
    Thin, explicit wrapper around Fernet so call sites read as intent
    ("encrypt this journal entry") rather than crypto-library plumbing, and
    so there's exactly one place that knows the key.

    Fernet already gives us: AES-128-CBC + HMAC (authenticated encryption,
    so tampering is detected, not just confidentiality), a random IV per
    call (two encryptions of the same plaintext never produce the same
    ciphertext), and a timestamp for optional TTL checks (unused here).
    """

    def __init__(self, key: str):
        # Fails fast and loudly at startup if the key is malformed, rather
        # than at the first user's first journal entry.
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str | None) -> bytes | None:
        if plaintext is None:
            return None
        if plaintext == "":
            # Deliberately not encrypting empty string to a real ciphertext
            # -- there's nothing to protect, and it avoids a confusing
            # round trip where "" comes back as None or vice versa.
            return b""
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes | None) -> str | None:
        if ciphertext is None:
            return None
        if ciphertext == b"":
            return ""
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as exc:
            # Never surface raw crypto internals to a caller, but never
            # silently return None either -- a decryption failure on a
            # sensitive field is an integrity incident, not a normal
            # "missing data" case, and must be visible as one.
            raise ValueError(
                "Failed to decrypt field: ciphertext is invalid or was "
                "encrypted with a different key."
            ) from exc


def get_field_encryptor(settings: Settings = Depends(get_settings)) -> FieldEncryptor:
    return FieldEncryptor(settings.field_encryption_key)
