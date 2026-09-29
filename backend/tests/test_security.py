import pytest
from cryptography.fernet import Fernet

from app.security import FieldEncryptor


@pytest.fixture
def key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def encryptor(key) -> FieldEncryptor:
    return FieldEncryptor(key)


def test_round_trip_preserves_plaintext(encryptor):
    plaintext = "felt the urge around midnight after doomscrolling, resisted"
    ciphertext = encryptor.encrypt(plaintext)

    assert ciphertext != plaintext.encode()
    assert encryptor.decrypt(ciphertext) == plaintext


def test_same_plaintext_produces_different_ciphertext_each_time(encryptor):
    """
    Fernet includes a random IV per encryption. Two journal entries with
    identical text should not be distinguishable as identical from the
    stored ciphertext alone.
    """
    a = encryptor.encrypt("skipped gym today")
    b = encryptor.encrypt("skipped gym today")

    assert a != b
    assert encryptor.decrypt(a) == encryptor.decrypt(b) == "skipped gym today"


def test_none_passes_through_as_none(encryptor):
    assert encryptor.encrypt(None) is None
    assert encryptor.decrypt(None) is None


def test_empty_string_round_trips_without_becoming_a_real_ciphertext(encryptor):
    ciphertext = encryptor.encrypt("")
    assert ciphertext == b""
    assert encryptor.decrypt(ciphertext) == ""


def test_wrong_key_cannot_decrypt(key):
    encryptor_a = FieldEncryptor(key)
    encryptor_b = FieldEncryptor(Fernet.generate_key().decode())

    ciphertext = encryptor_a.encrypt("sensitive trigger context")

    with pytest.raises(ValueError, match="Failed to decrypt"):
        encryptor_b.decrypt(ciphertext)


def test_tampered_ciphertext_is_rejected_not_silently_corrupted(encryptor):
    ciphertext = bytearray(encryptor.encrypt("resisted, used the if-then plan"))
    ciphertext[-1] ^= 0xFF  # flip bits near the HMAC tag

    with pytest.raises(ValueError, match="Failed to decrypt"):
        encryptor.decrypt(bytes(ciphertext))


def test_malformed_key_fails_at_construction_not_at_first_use():
    with pytest.raises(Exception):
        FieldEncryptor("not-a-valid-fernet-key")
