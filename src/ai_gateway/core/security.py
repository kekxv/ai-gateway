import base64
import binascii
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet

from ai_gateway.core.config import Settings

TokenType = Literal["access", "refresh"]

_PASSWORD_HASHER = PasswordHasher(type=Type.ID)
_JWT_ALGORITHM = "HS256"
_TOTP_SECRET_PATTERN = re.compile(r"[A-Z2-7]+")
_TOTP_SECRET_IGNORED_CHARACTERS = " \t\n\r\v\f-"
_FERNET_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}=")
_KNOWN_WEAK_SECRET_NAMES = {
    "changeme",
    "changethissecret",
    "development",
    "example",
    "password",
    "replacewithalongrandomsecret",
    "replacewithafernetkey",
    "secret",
    "yourjwtsecret",
}


class InvalidTokenTypeError(jwt.InvalidTokenError):
    pass


def validate_jwt_secret_strength(secret: str) -> None:
    """Validate production JWT secret shape using conservative heuristics.

    This check enforces a minimum key size and rejects values that are clearly
    placeholders or generated from a short repeating pattern. It cannot prove
    that an operator supplied cryptographically random material.
    """

    if any(character.isspace() for character in secret):
        raise ValueError("must not contain whitespace")
    try:
        encoded = secret.encode("utf-8")
    except UnicodeError as exc:  # pragma: no cover - str.encode normally succeeds
        raise ValueError("must be valid UTF-8") from exc
    if len(encoded) < 32:
        raise ValueError("must contain at least 32 UTF-8 bytes")
    normalized = re.sub(r"[^a-z0-9]", "", secret.casefold())
    if normalized in _KNOWN_WEAK_SECRET_NAMES:
        raise ValueError("must not use a known placeholder")
    if _is_obviously_repeated(secret):
        raise ValueError("must not use an obviously repeated value")


def validate_fernet_key_strength(secret: str) -> None:
    """Validate a production Fernet key's encoding and obvious weak patterns."""

    if any(character.isspace() for character in secret):
        raise ValueError("must not contain whitespace")
    if _FERNET_KEY_PATTERN.fullmatch(secret) is None:
        raise ValueError("must be a URL-safe Base64 key encoding 32 bytes")
    try:
        decoded = base64.b64decode(secret.encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ValueError("must be a URL-safe Base64 key encoding 32 bytes") from exc
    if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode("ascii") != secret:
        raise ValueError("must be a canonical URL-safe Base64 key encoding 32 bytes")
    if _is_obviously_repeated(decoded):
        raise ValueError("must not decode to an obviously repeated value")


def _is_obviously_repeated(value: str | bytes) -> bool:
    if not value:
        return True
    if len(set(value)) <= 3:
        return True
    # Searching the doubled value finds every possible period (including
    # periods longer than 16) in linear time without an unbounded loop.
    return len(value) > 1 and (value + value).find(value, 1) != len(value)


def validate_totp_secret(secret: str) -> str:
    normalized = secret.translate(str.maketrans("", "", _TOTP_SECRET_IGNORED_CHARACTERS)).upper()
    if not normalized:
        raise ValueError("TOTP secret must not be empty")
    if len(normalized) > 128:
        raise ValueError("TOTP secret must contain at most 128 Base32 characters")
    if _TOTP_SECRET_PATTERN.fullmatch(normalized) is None:
        raise ValueError("TOTP secret must be a valid Base32 value")

    padded = normalized + "=" * (-len(normalized) % 8)
    try:
        decoded = base64.b32decode(padded)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("TOTP secret must be a valid Base32 value") from exc
    if len(decoded) < 20:
        raise ValueError("TOTP secret must decode to at least 20 bytes")
    return normalized


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(encoded_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def issue_access_token(*, user_id: int, settings: Settings) -> str:
    return _issue_token(
        user_id=user_id,
        token_type="access",
        lifetime=timedelta(minutes=settings.jwt_access_minutes),
        settings=settings,
    )


def issue_refresh_token(*, user_id: int, settings: Settings) -> str:
    return _issue_token(
        user_id=user_id,
        token_type="refresh",
        lifetime=timedelta(days=settings.jwt_refresh_days),
        settings=settings,
    )


def decode_token(
    token: str,
    *,
    expected_type: TokenType,
    settings: Settings,
) -> dict[str, Any]:
    claims: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[_JWT_ALGORITHM],
        issuer=settings.jwt_issuer,
        options={"require": ["sub", "type", "iss", "iat", "exp", "jti"]},
    )
    if claims["type"] != expected_type:
        raise InvalidTokenTypeError("invalid token type")
    return claims


def token_issued_at(claims: Mapping[str, Any]) -> datetime:
    """Return a token's UTC issue time as a naive database-compatible datetime."""
    issued_at_microseconds = claims.get("iat_us")
    if isinstance(issued_at_microseconds, int) and not isinstance(issued_at_microseconds, bool):
        return datetime.fromtimestamp(issued_at_microseconds / 1_000_000, tz=UTC).replace(
            tzinfo=None
        )
    return datetime.fromtimestamp(int(claims["iat"]), tz=UTC).replace(tzinfo=None)


def encrypt_secret(secret: str, *, settings: Settings) -> bytes:
    return _fernet(settings).encrypt(secret.encode())


def decrypt_secret(encrypted_secret: bytes, *, settings: Settings) -> str:
    return _fernet(settings).decrypt(encrypted_secret).decode()


def _issue_token(
    *,
    user_id: int,
    token_type: TokenType,
    lifetime: timedelta,
    settings: Settings,
) -> str:
    issued_at = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "type": token_type,
        "iss": settings.jwt_issuer,
        "iat": issued_at,
        "iat_us": int(issued_at.timestamp()) * 1_000_000 + issued_at.microsecond,
        "exp": issued_at + lifetime,
        "jti": str(uuid4()),
    }
    return jwt.encode(
        claims,
        settings.jwt_secret.get_secret_value(),
        algorithm=_JWT_ALGORITHM,
    )


def _fernet(settings: Settings) -> Fernet:
    return Fernet(settings.encryption_key.get_secret_value().encode())
