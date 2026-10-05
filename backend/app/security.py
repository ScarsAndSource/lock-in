"""
JWT verification (HS256 shared secret OR JWKS asymmetric) and field-level
encryption with key rotation.

Algorithm-confusion guard: the verification algorithm is chosen by SERVER
CONFIG (auth_mode), never by the token's own header. In jwks mode an
HS256-signed token is rejected outright.
"""
from __future__ import annotations

import asyncio
import time
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import Settings, get_settings

_bearer_scheme = HTTPBearer(auto_error=False)
_JWKS_ALGORITHMS = ["ES256", "RS256"]


class JWKSUnavailable(Exception):
    """Signing keys could not be fetched and none are cached."""


class JWKSCache:
    """Caches the project's public signing keys; refetches at most every
    `min_refresh_seconds` on demand (key rotation) and serves stale keys
    rather than locking everyone out if Supabase is briefly unreachable."""

    def __init__(self, url: str, ttl_seconds: int = 3600, min_refresh_seconds: int = 30, clock=time.monotonic):
        self._url = url
        self._ttl = ttl_seconds
        self._min_refresh = min_refresh_seconds
        self._clock = clock
        self._keys: dict | None = None
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self, force: bool = False) -> dict:
        async with self._lock:
            now = self._clock()
            age = now - self._fetched_at
            if self._keys is not None:
                if not force and age < self._ttl:
                    return self._keys
                if force and age < self._min_refresh:
                    return self._keys
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(self._url)
                    resp.raise_for_status()
                    data = resp.json()
                if not isinstance(data, dict) or not data.get("keys"):
                    raise ValueError("JWKS document has no keys")
            except (httpx.HTTPError, ValueError) as exc:
                if self._keys is not None:
                    return self._keys
                raise JWKSUnavailable(str(exc)) from exc
            self._keys, self._fetched_at = data, now
            return data


_jwks_caches: dict[str, JWKSCache] = {}


def _get_jwks_cache(settings: Settings) -> JWKSCache:
    cache = _jwks_caches.get(settings.supabase_jwks_url)
    if cache is None:
        cache = _jwks_caches[settings.supabase_jwks_url] = JWKSCache(settings.supabase_jwks_url)
    return cache


def decode_supabase_jwt(token: str, settings: Settings, jwks: dict | None = None) -> dict:
    """Raises JWTError on any failure (expired, bad sig, wrong aud, missing exp/sub...)."""
    kwargs: dict = {
        "audience": settings.supabase_jwt_audience,
        "options": {"require_exp": True, "require_sub": True},
    }
    if settings.supabase_jwt_issuer:
        kwargs["issuer"] = settings.supabase_jwt_issuer

    if settings.auth_mode == "jwks":
        if not jwks:
            raise JWTError("No signing keys available.")
        return jwt.decode(token, jwks, algorithms=_JWKS_ALGORITHMS, **kwargs)
    return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], **kwargs)


async def _verify(token: str, settings: Settings) -> dict:
    if settings.auth_mode == "hs256":
        return decode_supabase_jwt(token, settings)
    cache = _get_jwks_cache(settings)
    jwks = await cache.get()
    try:
        return decode_supabase_jwt(token, settings, jwks)
    except JWTError:
        fresh = await cache.get(force=True)  # unknown kid after rotation -> one throttled refetch
        if fresh is jwks:
            raise
        return decode_supabase_jwt(token, settings, fresh)


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> UUID:
    """Every route touching user data depends on this -- no trusted internal callers."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token.")
    try:
        payload = await _verify(credentials.credentials, settings)
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.") from exc
    except JWKSUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth keys temporarily unavailable.") from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject claim.")
    try:
        return UUID(subject)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token subject is not a valid user id.") from exc


class FieldEncryptor:
    """
    Fernet (AES-128-CBC + HMAC, random IV) behind MultiFernet so keys can be
    rotated: the FIRST key encrypts, ALL keys can decrypt. Rotation recipe:
    new key -> FIELD_ENCRYPTION_KEY, old key -> FIELD_ENCRYPTION_OLD_KEYS,
    optionally re-encrypt rows with rotate(), then drop the old key.
    """

    def __init__(self, key: str, old_keys: list[str] | tuple[str, ...] = ()):
        keys = [key, *old_keys]
        # Fails fast at construction if any key is malformed.
        self._multi = MultiFernet([Fernet(k.encode() if isinstance(k, str) else k) for k in keys])

    def encrypt(self, plaintext: str | None) -> bytes | None:
        if plaintext is None:
            return None
        if plaintext == "":
            return b""
        return self._multi.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes | None) -> str | None:
        if ciphertext is None:
            return None
        if ciphertext == b"":
            return ""
        try:
            return self._multi.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError(
                "Failed to decrypt field: ciphertext is invalid or was encrypted with an unknown key."
            ) from exc

    def rotate(self, ciphertext: bytes) -> bytes:
        """Re-encrypt under the primary key."""
        if ciphertext in (None, b""):
            return ciphertext
        try:
            return self._multi.rotate(ciphertext)
        except InvalidToken as exc:
            raise ValueError("Failed to rotate field: ciphertext is invalid.") from exc


def get_field_encryptor(settings: Settings = Depends(get_settings)) -> FieldEncryptor:
    return FieldEncryptor(settings.field_encryption_key, settings.old_encryption_keys)
