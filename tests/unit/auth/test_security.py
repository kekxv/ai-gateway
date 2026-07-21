from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from jwt import InvalidTokenError

from ai_gateway.core.config import Settings
from ai_gateway.core.security import (
    decode_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    issue_access_token,
    issue_refresh_token,
    verify_password,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        jwt_secret="test-jwt-secret-that-is-long-enough",
        encryption_key=Fernet.generate_key().decode(),
    )


def test_password_hash_is_not_plaintext() -> None:
    password = "correct horse battery staple"

    encoded = hash_password(password)

    assert encoded != password
    assert encoded.startswith("$argon2id$")
    assert verify_password(password, encoded)
    assert not verify_password("wrong password", encoded)
    assert not verify_password(password, "not-an-argon2-hash")


def test_access_token_has_subject_type_and_expiry(settings: Settings) -> None:
    token = issue_access_token(user_id=7, settings=settings)

    claims = decode_token(token, expected_type="access", settings=settings)

    assert claims["sub"] == "7"
    assert claims["type"] == "access"
    assert claims["iss"] == "ai-gateway"
    assert claims["exp"] > claims["iat"]
    assert datetime.fromtimestamp(claims["exp"], tz=UTC) > datetime.now(UTC)
    assert claims["jti"]


def test_refresh_token_cannot_be_decoded_as_access(settings: Settings) -> None:
    token = issue_refresh_token(user_id=7, settings=settings)

    with pytest.raises(InvalidTokenError, match="token type"):
        decode_token(token, expected_type="access", settings=settings)


def test_secret_encryption_round_trip(settings: Settings) -> None:
    encrypted = encrypt_secret("never-store-this-in-plaintext", settings=settings)

    assert isinstance(encrypted, bytes)
    assert b"never-store-this-in-plaintext" not in encrypted
    assert decrypt_secret(encrypted, settings=settings) == "never-store-this-in-plaintext"
