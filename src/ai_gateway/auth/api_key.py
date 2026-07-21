from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, NoReturn

from fastapi import Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from ai_gateway.auth.service import raise_auth_error
from ai_gateway.core.enums import ApiKeyScope
from ai_gateway.db.models import ApiKey
from ai_gateway.db.session import get_session


@dataclass(frozen=True, slots=True)
class ApiKeyPrincipal:
    api_key_id: int
    user_id: int
    scope: ApiKeyScope
    provider_ids: frozenset[int] = frozenset()
    model_ids: frozenset[int] = frozenset()


def authorize_scope(
    principal: ApiKeyPrincipal,
    model_id: int,
    provider_id: int,
) -> bool:
    if principal.scope is ApiKeyScope.ALL:
        return True
    provider_allowed = provider_id in principal.provider_ids
    model_allowed = model_id in principal.model_ids
    if principal.scope is ApiKeyScope.PROVIDERS:
        return provider_allowed
    if principal.scope is ApiKeyScope.MODELS:
        return model_allowed
    return provider_allowed and model_allowed


async def authenticate_api_key(raw_key: str, session: AsyncSession) -> ApiKeyPrincipal:
    if not raw_key.startswith("sk-gw-"):
        _raise_invalid_api_key()

    digest = sha256(raw_key.encode()).digest()
    candidates = (
        await session.scalars(
            select(ApiKey)
            .where(ApiKey.key_prefix == raw_key[:12])
            .options(
                joinedload(ApiKey.user),
                selectinload(ApiKey.provider_links),
                selectinload(ApiKey.model_links),
            )
            .execution_options(populate_existing=True)
        )
    ).all()
    api_key = next(
        (candidate for candidate in candidates if hmac.compare_digest(candidate.key_hash, digest)),
        None,
    )
    if api_key is None or not api_key.is_active or _is_expired(api_key.expires_at):
        _raise_invalid_api_key()
    if not api_key.user.is_active:
        raise_auth_error(status.HTTP_403_FORBIDDEN, "user_disabled", "User is disabled")

    api_key.last_used_at = datetime.now(UTC).replace(tzinfo=None)
    principal = ApiKeyPrincipal(
        api_key_id=api_key.id,
        user_id=api_key.user_id,
        scope=api_key.scope,
        provider_ids=frozenset(link.provider_id for link in api_key.provider_links),
        model_ids=frozenset(link.model_id for link in api_key.model_links),
    )
    await session.commit()
    return principal


def extract_api_key(request: Request) -> str:
    credentials: list[str] = []
    for authorization in request.headers.getlist("authorization"):
        scheme, separator, value = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not value.strip():
            _raise_invalid_api_key()
        credentials.append(value.strip())

    for header_name in ("x-api-key", "x-goog-api-key"):
        for header_value in request.headers.getlist(header_name):
            if not header_value.strip():
                _raise_invalid_api_key()
            credentials.append(header_value.strip())

    if not credentials:
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "authentication_required",
            "An API key is required",
            authenticate=True,
        )
    if len(set(credentials)) > 1:
        raise_auth_error(
            status.HTTP_400_BAD_REQUEST,
            "ambiguous_credentials",
            "Credential headers contain different API keys",
        )
    return credentials[0]


async def get_api_key_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiKeyPrincipal:
    return await authenticate_api_key(extract_api_key(request), session)


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        return expires_at <= datetime.now(UTC).replace(tzinfo=None)
    return expires_at <= datetime.now(UTC)


def _raise_invalid_api_key() -> NoReturn:
    raise_auth_error(
        status.HTTP_401_UNAUTHORIZED,
        "invalid_api_key",
        "Invalid or expired API key",
        authenticate=True,
    )
