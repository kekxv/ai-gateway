from typing import NoReturn

import pyotp
from fastapi import HTTPException, status
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.config import Settings
from ai_gateway.core.security import (
    InvalidTokenTypeError,
    decode_token,
    decrypt_secret,
    hash_password,
    issue_access_token,
    verify_password,
)
from ai_gateway.db.models import Account, RegistrationLock, User

_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$Mzg0czBoazgzYm9Ba0lsTg$"
    "GqvI/2Blf7Y7Kq4hTZQONhxCM7Ez3cm66GaR5eWvqJY"
)


async def register_user(
    *,
    session: AsyncSession,
    email: str,
    password: str,
) -> User:
    normalized_email = email.strip().lower()
    await session.execute(
        insert(RegistrationLock).values(id=1).on_duplicate_key_update(id=RegistrationLock.id)
    )
    registration = await session.scalar(
        select(RegistrationLock).where(RegistrationLock.id == 1).with_for_update()
    )
    if registration is None:
        raise RuntimeError("registration lock was not created")
    if not registration.enabled:
        await session.rollback()
        raise_auth_error(
            status.HTTP_403_FORBIDDEN,
            "registration_disabled",
            "Public registration is disabled",
        )
    existing_user_id = await session.scalar(select(User.id).limit(1))
    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        role="admin" if existing_user_id is None else "user",
        account=Account(),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise_auth_error(
            status.HTTP_409_CONFLICT,
            "email_exists",
            "A user with this email already exists",
        )
    return user


async def registration_enabled(*, session: AsyncSession) -> bool:
    enabled = await session.scalar(select(RegistrationLock.enabled).where(RegistrationLock.id == 1))
    return True if enabled is None else enabled


async def change_password(
    *,
    session: AsyncSession,
    user_id: int,
    current_password: str,
    new_password: str,
) -> None:
    user = await _locked_user(session=session, user_id=user_id)
    if not verify_password(current_password, user.password_hash):
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Invalid current password",
            authenticate=True,
        )
    user.password_hash = hash_password(new_password)
    await session.commit()


async def disable_totp(
    *,
    session: AsyncSession,
    user_id: int,
    current_password: str,
    code: str,
    settings: Settings,
) -> None:
    user = await _locked_user(session=session, user_id=user_id)
    if not user.totp_enabled or user.totp_secret_encrypted is None:
        raise_auth_error(
            status.HTTP_409_CONFLICT,
            "totp_not_enabled",
            "TOTP is not enabled",
        )
    if not verify_password(current_password, user.password_hash):
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Invalid current password",
            authenticate=True,
        )
    secret = decrypt_secret(user.totp_secret_encrypted, settings=settings)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_totp",
            "Invalid TOTP code",
            authenticate=True,
        )
    user.totp_enabled = False
    user.totp_secret_encrypted = None
    user.pending_totp_secret_encrypted = None
    await session.commit()


async def _locked_user(*, session: AsyncSession, user_id: int) -> User:
    user = await session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_token",
            "Invalid or expired token",
            authenticate=True,
        )
    return user


def raise_auth_error(
    status_code: int,
    code: str,
    message: str,
    *,
    authenticate: bool = False,
) -> NoReturn:
    headers = {"WWW-Authenticate": "Bearer"} if authenticate else None
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
        headers=headers,
    )


async def authenticate_user(
    *,
    session: AsyncSession,
    email: str,
    password: str,
    totp_code: str | None,
    settings: Settings,
) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    if not verify_password(password, password_hash) or user is None:
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Invalid email or password",
            authenticate=True,
        )
    if not user.is_active:
        raise_auth_error(status.HTTP_403_FORBIDDEN, "user_disabled", "User is disabled")
    if user.totp_enabled:
        if totp_code is None:
            raise_auth_error(
                status.HTTP_401_UNAUTHORIZED,
                "totp_required",
                "A TOTP code is required",
                authenticate=True,
            )
        if user.totp_secret_encrypted is None:
            raise_auth_error(
                status.HTTP_401_UNAUTHORIZED,
                "invalid_totp",
                "Invalid TOTP code",
                authenticate=True,
            )
        secret = decrypt_secret(user.totp_secret_encrypted, settings=settings)
        if not pyotp.TOTP(secret).verify(totp_code, valid_window=1):
            raise_auth_error(
                status.HTTP_401_UNAUTHORIZED,
                "invalid_totp",
                "Invalid TOTP code",
                authenticate=True,
            )
    return user


async def refresh_access_token(
    *,
    session: AsyncSession,
    refresh_token: str,
    settings: Settings,
) -> str:
    try:
        claims = decode_token(refresh_token, expected_type="refresh", settings=settings)
    except InvalidTokenTypeError:
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_token_type",
            "A refresh token is required",
            authenticate=True,
        )
    except InvalidTokenError:
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_token",
            "Invalid or expired token",
            authenticate=True,
        )

    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_token",
            "Invalid or expired token",
            authenticate=True,
        )
    user = await session.get(User, user_id)
    if user is None:
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_token",
            "Invalid or expired token",
            authenticate=True,
        )
    if not user.is_active:
        raise_auth_error(status.HTTP_403_FORBIDDEN, "user_disabled", "User is disabled")
    return issue_access_token(user_id=user.id, settings=settings)
