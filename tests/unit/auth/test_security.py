from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.fernet import Fernet
from freezegun import freeze_time
from jwt import InvalidTokenError

from ai_gateway.core import security
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


def test_totp_secret_normalizes_formatted_base32_and_preserves_entropy() -> None:
    normalized = security.validate_totp_secret("jbsw y3dp-ehpk3pxp jbsw y3dp-ehpk3pxp")

    assert normalized == "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


@pytest.mark.parametrize(
    ("secret", "message"),
    [
        ("---   ", "must not be empty"),
        ("NOT-BASE32-0189", "valid Base32"),
        ("JBSWY3DPEHPK3PXP", "at least 20 bytes"),
        ("A" * 129, "at most 128"),
    ],
)
def test_totp_secret_rejects_unsafe_values_without_echoing_them(
    secret: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message) as error:
        security.validate_totp_secret(secret)

    assert secret not in str(error.value)


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


def test_access_token_preserves_microsecond_issue_time(settings: Settings) -> None:
    issued_at = datetime(2026, 7, 28, 12, 34, 56, 123456, tzinfo=UTC)

    with freeze_time(issued_at):
        token = issue_access_token(user_id=7, settings=settings)
        claims = decode_token(token, expected_type="access", settings=settings)

    assert hasattr(security, "token_issued_at")
    assert claims["iat_us"] == 1785242096123456
    assert security.token_issued_at(claims) == issued_at.replace(tzinfo=None)


def test_refresh_token_cannot_be_decoded_as_access(settings: Settings) -> None:
    token = issue_refresh_token(user_id=7, settings=settings)

    with pytest.raises(InvalidTokenError, match="token type"):
        decode_token(token, expected_type="access", settings=settings)


def make_token(settings: Settings, **claim_overrides: object) -> str:
    issued_at = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": "7",
        "type": "access",
        "iss": settings.jwt_issuer,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=5),
        "jti": "test-token-id",
    }
    claims.update(claim_overrides)
    return jwt.encode(
        claims,
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def test_decode_token_rejects_missing_required_claim(settings: Settings) -> None:
    issued_at = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "7",
            "type": "access",
            "iss": settings.jwt_issuer,
            "iat": issued_at,
            "exp": issued_at + timedelta(minutes=5),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(InvalidTokenError):
        decode_token(token, expected_type="access", settings=settings)


def test_decode_token_rejects_wrong_issuer(settings: Settings) -> None:
    token = make_token(settings, iss="another-service")

    with pytest.raises(InvalidTokenError):
        decode_token(token, expected_type="access", settings=settings)


def test_decode_token_rejects_tampered_signature(settings: Settings) -> None:
    token = make_token(settings)
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    tampered = ".".join((header, payload, f"{replacement}{signature[1:]}"))

    with pytest.raises(InvalidTokenError):
        decode_token(tampered, expected_type="access", settings=settings)


def test_decode_token_rejects_expired_token(settings: Settings) -> None:
    token = make_token(settings, exp=datetime.now(UTC) - timedelta(seconds=1))

    with pytest.raises(InvalidTokenError):
        decode_token(token, expected_type="access", settings=settings)


def test_secret_encryption_round_trip(settings: Settings) -> None:
    encrypted = encrypt_secret("never-store-this-in-plaintext", settings=settings)

    assert isinstance(encrypted, bytes)
    assert b"never-store-this-in-plaintext" not in encrypted
    assert decrypt_secret(encrypted, settings=settings) == "never-store-this-in-plaintext"
