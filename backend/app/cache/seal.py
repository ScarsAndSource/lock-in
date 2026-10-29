"""Encrypt/decrypt cached values with the same Fernet keys as stored chats, so Redis never holds plaintext."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.security import FieldEncryptor


@lru_cache(maxsize=1)
def _encryptor() -> FieldEncryptor:
    s = get_settings()
    return FieldEncryptor(s.field_encryption_key, s.old_encryption_keys)


def seal(text: str) -> bytes | None:
    return _encryptor().encrypt(text)


def unseal(blob: bytes) -> str | None:
    """None when the blob is unreadable (key rotated away, corrupted): treat it as a cache miss."""
    try:
        return _encryptor().decrypt(blob)
    except ValueError:
        return None
