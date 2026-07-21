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


class InvalidTokenTypeError(jwt.InvalidTokenError):
    pass


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
