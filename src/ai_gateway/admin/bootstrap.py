from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ai_gateway.core.config import get_settings
from ai_gateway.core.security import encrypt_secret, hash_password, validate_totp_secret
from ai_gateway.db.models import Account, User
from ai_gateway.db.session import get_engine_for_url, get_session_factory_for_engine


class AdminEmailConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AdminBootstrapResult:
    user: User
    created: bool


async def _load_user(session: AsyncSession, email: str) -> User | None:
    return cast(User | None, await session.scalar(select(User).where(User.email == email)))


def _existing_user_result(user: User) -> AdminBootstrapResult:
    if user.role != "admin":
        raise AdminEmailConflictError(
            f"email {user.email!r} belongs to a regular user; refusing to promote it"
        )
    return AdminBootstrapResult(user=user, created=False)


async def create_admin(
    email: str,
    password: str,
    *,
    totp_secret: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> AdminBootstrapResult:
    normalized_email = email.strip()
    if len(normalized_email) < 3 or len(normalized_email) > 320:
        raise ValueError("email must contain between 3 and 320 characters")

    owned_engine: AsyncEngine | None = None
    settings = None
    if session_factory is None:
        settings = get_settings()
        owned_engine = get_engine_for_url(settings.database_url)
        session_factory = get_session_factory_for_engine(owned_engine)

    try:
        async with session_factory() as session:
            existing = await _load_user(session, normalized_email)
            if existing is not None:
                return _existing_user_result(existing)

            if not password:
                raise ValueError("password must not be empty")

            encrypted_totp_secret: bytes | None = None
            if totp_secret is not None:
                validated_totp_secret = validate_totp_secret(totp_secret)
                settings = settings or get_settings()
                encrypted_totp_secret = encrypt_secret(
                    validated_totp_secret,
                    settings=settings,
                )

            admin = User(
                email=normalized_email,
                password_hash=hash_password(password),
                role="admin",
                totp_enabled=encrypted_totp_secret is not None,
                totp_secret_encrypted=encrypted_totp_secret,
                account=Account(),
            )
            session.add(admin)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                race_winner = await _load_user(session, normalized_email)
                if race_winner is None:
                    raise
                return _existing_user_result(race_winner)
            await session.refresh(admin)
            return AdminBootstrapResult(user=admin, created=True)
    finally:
        if owned_engine is not None:
            await owned_engine.dispose()
