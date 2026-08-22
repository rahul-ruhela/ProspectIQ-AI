"""Tests for authentication primitives and secret handling."""
from __future__ import annotations

import time

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decrypt_secret,
    decode_token,
    encrypt_secret,
    hash_password,
    mask_secret,
    verify_password,
)


def test_password_hashing_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password entirely", hashed)


def test_hash_is_salted() -> None:
    assert hash_password("same password") != hash_password("same password")


def test_passwords_longer_than_the_bcrypt_limit_still_work() -> None:
    # bcrypt truncates at 72 bytes and raises on longer input if not handled.
    long_password = "a" * 200
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed)


def test_verify_password_rejects_a_malformed_hash() -> None:
    assert not verify_password("anything", "not-a-bcrypt-hash")


def test_access_and_refresh_tokens_are_not_interchangeable() -> None:
    access = create_access_token("user-1", role="admin")
    refresh = create_refresh_token("user-1")

    assert decode_token(access, expected_type="access")["sub"] == "user-1"
    assert decode_token(access, expected_type="refresh") is None
    assert decode_token(refresh, expected_type="refresh")["sub"] == "user-1"
    assert decode_token(refresh, expected_type="access") is None


def test_token_carries_claims_and_a_unique_id() -> None:
    first = decode_token(create_access_token("user-1", role="admin"))
    time.sleep(0.01)
    second = decode_token(create_access_token("user-1", role="admin"))
    assert first["role"] == "admin"
    assert first["jti"] != second["jti"]


def test_tampered_token_is_rejected() -> None:
    token = create_access_token("user-1")
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    assert decode_token(tampered) is None


def test_secrets_round_trip_and_do_not_store_plaintext() -> None:
    secret = "sk-ant-super-secret-value"
    encrypted = encrypt_secret(secret)
    assert secret not in encrypted
    assert decrypt_secret(encrypted) == secret


def test_decrypting_garbage_returns_empty_rather_than_raising() -> None:
    assert decrypt_secret("not-a-fernet-token") == ""


def test_mask_secret_hides_the_middle() -> None:
    masked = mask_secret("sk-ant-1234567890abcdef")
    assert masked.startswith("sk-a")
    assert masked.endswith("cdef")
    assert "1234567890" not in masked
    assert mask_secret("short") == "*****"
    assert mask_secret("") == ""
