from typing import Annotated, Any

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.service import raise_auth_error
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.security import decode_token, token_issued_at
from ai_gateway.db.models import User
from ai_gateway.db.session import get_session

_bearer = HTTPBearer(auto_error=False)


def _check_token_revocation(user: User, claims: dict[str, Any]) -> None:
    """Reject tokens issued before the user's invalidation timestamp."""
    invalidated_before = getattr(user, "tokens_invalidated_before", None)
    if invalidated_before is not None:
        issued_at = token_issued_at(claims)
        if issued_at < invalidated_before:
            raise_auth_error(
                status.HTTP_401_UNAUTHORIZED,
                "invalid_token",
                "Invalid or expired token",
                authenticate=True,
            )


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "authentication_required",
            "Bearer authentication is required",
            authenticate=True,
        )
    try:
        claims = decode_token(credentials.credentials, expected_type="access", settings=settings)
        user_id = int(claims["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
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
    _check_token_revocation(user, claims)
    return user


async def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise_auth_error(status.HTTP_403_FORBIDDEN, "admin_required", "Admin access is required")
    return user
