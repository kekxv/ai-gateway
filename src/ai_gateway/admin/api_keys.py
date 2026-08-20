from __future__ import annotations

import secrets
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.auth.dependencies import admin_user, current_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.core.datetime import UtcDatetime
from ai_gateway.core.enums import ApiKeyScope
from ai_gateway.db.models import ApiKey, ApiKeyModel, ApiKeyProvider, Model, Provider, User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/admin/api-keys", tags=["admin-api-keys"])
self_router = APIRouter(prefix="/user/api-keys", tags=["user-api-keys"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
CurrentUser = Annotated[User, Depends(current_user)]
SelfApiKeyScope = Literal[ApiKeyScope.ALL, ApiKeyScope.MODELS]


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    name: str = Field(min_length=1, max_length=255)
    scope: ApiKeyScope = ApiKeyScope.ALL
    is_active: bool = True
    expires_at: datetime | None = None
    provider_ids: list[int] = Field(default_factory=list)
    model_ids: list[int] = Field(default_factory=list)


class ApiKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    scope: ApiKeyScope | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None
    provider_ids: list[int] | None = None
    model_ids: list[int] | None = None


class ApiKeyResponse(BaseModel):
    id: int
    user_id: int
    name: str
    key_prefix: str
    scope: ApiKeyScope
    is_active: bool
    expires_at: UtcDatetime | None
    last_used_at: UtcDatetime | None
    created_at: UtcDatetime
    provider_ids: list[int]
    model_ids: list[int]


class ApiKeyCreatedResponse(ApiKeyResponse):
    key: str


class SelfApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    scope: SelfApiKeyScope = ApiKeyScope.ALL
    is_active: bool = True
    expires_at: datetime | None = None
    model_ids: list[int] = Field(default_factory=list)


class SelfApiKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    scope: SelfApiKeyScope | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None
    model_ids: list[int] | None = None


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    session: Session,
    _: AdminUser,
) -> ApiKeyCreatedResponse:
    await _validate_owner(session, payload.user_id)
    provider_ids = set(payload.provider_ids)
    model_ids = set(payload.model_ids)
    await _validate_relation_ids(session, provider_ids=provider_ids, model_ids=model_ids)
    api_key, raw_key = _new_api_key(
        user_id=payload.user_id,
        name=payload.name,
        scope=payload.scope,
        is_active=payload.is_active,
        expires_at=_database_datetime(payload.expires_at),
        provider_ids=provider_ids,
        model_ids=model_ids,
    )
    session.add(api_key)
    await session.flush()
    await session.refresh(api_key, attribute_names=["created_at"])
    response = _created_response(api_key, raw_key)
    await session.commit()
    return response


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    session: Session,
    _: AdminUser,
    user_id: int | None = None,
) -> list[ApiKeyResponse]:
    query = (
        select(ApiKey)
        .options(selectinload(ApiKey.provider_links), selectinload(ApiKey.model_links))
        .order_by(ApiKey.id)
    )
    if user_id is not None:
        query = query.where(ApiKey.user_id == user_id)
    api_keys = (await session.scalars(query)).all()
    return [_api_key_response(api_key) for api_key in api_keys]


@router.get("/{api_key_id}", response_model=ApiKeyResponse)
async def get_api_key(api_key_id: int, session: Session, _: AdminUser) -> ApiKeyResponse:
    return _api_key_response(await _get_api_key(session, api_key_id))


@router.patch("/{api_key_id}", response_model=ApiKeyResponse)
@router.put("/{api_key_id}", response_model=ApiKeyResponse, include_in_schema=False)
async def update_api_key(
    api_key_id: int,
    payload: ApiKeyUpdate,
    session: Session,
    _: AdminUser,
) -> ApiKeyResponse:
    api_key = await _get_api_key(session, api_key_id)
    if payload.name is not None:
        api_key.name = payload.name
    if payload.scope is not None:
        api_key.scope = payload.scope
    if payload.is_active is not None:
        api_key.is_active = payload.is_active
    if "expires_at" in payload.model_fields_set:
        api_key.expires_at = _database_datetime(payload.expires_at)

    provider_ids = (
        set(payload.provider_ids)
        if payload.provider_ids is not None
        else {link.provider_id for link in api_key.provider_links}
    )
    model_ids = (
        set(payload.model_ids)
        if payload.model_ids is not None
        else {link.model_id for link in api_key.model_links}
    )
    await _validate_relation_ids(session, provider_ids=provider_ids, model_ids=model_ids)
    if payload.provider_ids is not None:
        api_key.provider_links = [
            ApiKeyProvider(provider_id=provider_id) for provider_id in sorted(provider_ids)
        ]
    if payload.model_ids is not None:
        api_key.model_links = [ApiKeyModel(model_id=model_id) for model_id in sorted(model_ids)]
    await session.flush()
    response = _api_key_response(api_key)
    await session.commit()
    return response


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(api_key_id: int, session: Session, _: AdminUser) -> Response:
    api_key = await _get_api_key(session, api_key_id)
    await session.delete(api_key)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{api_key_id}/rotate",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def rotate_api_key(
    api_key_id: int,
    session: Session,
    _: AdminUser,
) -> ApiKeyCreatedResponse:
    old_key = await _get_api_key(session, api_key_id, for_update=True)
    return await _rotate_locked_api_key(session, old_key)


@self_router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_own_api_key(
    payload: SelfApiKeyCreate,
    session: Session,
    user: CurrentUser,
) -> ApiKeyCreatedResponse:
    model_ids = set(payload.model_ids) if payload.scope is ApiKeyScope.MODELS else set()
    await _validate_self_model_ids(session, model_ids)
    api_key, raw_key = _new_api_key(
        user_id=user.id,
        name=payload.name,
        scope=payload.scope,
        is_active=payload.is_active,
        expires_at=_database_datetime(payload.expires_at),
        provider_ids=set(),
        model_ids=model_ids,
    )
    session.add(api_key)
    await session.flush()
    await session.refresh(api_key, attribute_names=["created_at"])
    response = _created_response(api_key, raw_key)
    await session.commit()
    return response


@self_router.get("", response_model=list[ApiKeyResponse])
async def list_own_api_keys(session: Session, user: CurrentUser) -> list[ApiKeyResponse]:
    api_keys = (
        await session.scalars(
            select(ApiKey)
            .where(ApiKey.user_id == user.id)
            .options(selectinload(ApiKey.provider_links), selectinload(ApiKey.model_links))
            .order_by(ApiKey.id)
        )
    ).all()
    return [_api_key_response(api_key) for api_key in api_keys]


@self_router.get("/{api_key_id}", response_model=ApiKeyResponse)
async def get_own_api_key(
    api_key_id: int,
    session: Session,
    user: CurrentUser,
) -> ApiKeyResponse:
    return _api_key_response(await _get_api_key(session, api_key_id, user_id=user.id))


@self_router.patch("/{api_key_id}", response_model=ApiKeyResponse)
async def update_own_api_key(
    api_key_id: int,
    payload: SelfApiKeyUpdate,
    session: Session,
    user: CurrentUser,
) -> ApiKeyResponse:
    api_key = await _get_api_key(session, api_key_id, user_id=user.id)
    target_scope = payload.scope if payload.scope is not None else api_key.scope
    if payload.name is not None:
        api_key.name = payload.name
    if payload.scope is not None:
        api_key.scope = payload.scope
        api_key.provider_links = []
    if payload.is_active is not None:
        api_key.is_active = payload.is_active
    if "expires_at" in payload.model_fields_set:
        api_key.expires_at = _database_datetime(payload.expires_at)

    if target_scope is ApiKeyScope.MODELS:
        model_ids = (
            set(payload.model_ids)
            if payload.model_ids is not None
            else {link.model_id for link in api_key.model_links}
        )
        await _validate_self_model_ids(session, model_ids)
        if payload.model_ids is not None or payload.scope is not None:
            api_key.model_links = [ApiKeyModel(model_id=model_id) for model_id in sorted(model_ids)]
    elif target_scope is ApiKeyScope.ALL:
        api_key.model_links = []
    elif payload.model_ids is not None:
        _raise_invalid_self_scope()

    await session.flush()
    response = _api_key_response(api_key)
    await session.commit()
    return response


@self_router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_own_api_key(
    api_key_id: int,
    session: Session,
    user: CurrentUser,
) -> Response:
    api_key = await _get_api_key(session, api_key_id, user_id=user.id)
    await session.delete(api_key)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@self_router.post(
    "/{api_key_id}/rotate",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def rotate_own_api_key(
    api_key_id: int,
    session: Session,
    user: CurrentUser,
) -> ApiKeyCreatedResponse:
    old_key = await _get_api_key(session, api_key_id, user_id=user.id, for_update=True)
    return await _rotate_locked_api_key(session, old_key)


async def _rotate_locked_api_key(
    session: AsyncSession,
    old_key: ApiKey,
) -> ApiKeyCreatedResponse:
    if not old_key.is_active:
        raise_auth_error(
            status.HTTP_409_CONFLICT,
            "api_key_inactive",
            "Only an active API key can be rotated",
        )
    provider_ids = {link.provider_id for link in old_key.provider_links}
    model_ids = {link.model_id for link in old_key.model_links}
    old_key.is_active = False
    replacement, raw_key = _new_api_key(
        user_id=old_key.user_id,
        name=old_key.name,
        scope=old_key.scope,
        is_active=True,
        expires_at=old_key.expires_at,
        provider_ids=provider_ids,
        model_ids=model_ids,
    )
    session.add(replacement)
    await session.flush()
    await session.refresh(replacement, attribute_names=["created_at"])
    response = _created_response(replacement, raw_key)
    await session.commit()
    return response


async def _get_api_key(
    session: AsyncSession,
    api_key_id: int,
    *,
    user_id: int | None = None,
    for_update: bool = False,
) -> ApiKey:
    query = select(ApiKey).where(ApiKey.id == api_key_id)
    if user_id is not None:
        query = query.where(ApiKey.user_id == user_id)
    query = query.options(selectinload(ApiKey.provider_links), selectinload(ApiKey.model_links))
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    api_key = await session.scalar(query)
    if api_key is None:
        _raise_api_key_not_found()
    return api_key


async def _validate_owner(session: AsyncSession, user_id: int) -> None:
    if await session.get(User, user_id) is None:
        raise_auth_error(status.HTTP_404_NOT_FOUND, "user_not_found", "User not found")


async def _validate_relation_ids(
    session: AsyncSession,
    *,
    provider_ids: set[int],
    model_ids: set[int],
) -> None:
    existing_provider_ids = set(
        await session.scalars(select(Provider.id).where(Provider.id.in_(provider_ids)))
    )
    existing_model_ids = set(await session.scalars(select(Model.id).where(Model.id.in_(model_ids))))
    if existing_provider_ids != provider_ids or existing_model_ids != model_ids:
        raise_auth_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_scope_reference",
            "One or more provider or model IDs do not exist",
        )


async def _validate_self_model_ids(session: AsyncSession, model_ids: set[int]) -> None:
    existing_model_ids = set(
        await session.scalars(
            select(Model.id).where(Model.id.in_(model_ids), Model.enabled.is_(True))
        )
    )
    if existing_model_ids != model_ids:
        raise_auth_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_scope_reference",
            "One or more model IDs are unavailable",
        )


def _raise_invalid_self_scope() -> NoReturn:
    raise_auth_error(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "invalid_scope_reference",
        "This API key scope cannot be managed by a regular user",
    )


def _new_api_key(
    *,
    user_id: int,
    name: str,
    scope: ApiKeyScope,
    is_active: bool,
    expires_at: datetime | None,
    provider_ids: set[int],
    model_ids: set[int],
) -> tuple[ApiKey, str]:
    raw_key = f"sk-gw-{secrets.token_urlsafe(32)}"
    api_key = ApiKey(
        user_id=user_id,
        name=name,
        key_prefix=raw_key[:12],
        key_hash=sha256(raw_key.encode()).digest(),
        scope=scope,
        is_active=is_active,
        expires_at=expires_at,
        provider_links=[
            ApiKeyProvider(provider_id=provider_id) for provider_id in sorted(provider_ids)
        ],
        model_links=[ApiKeyModel(model_id=model_id) for model_id in sorted(model_ids)],
    )
    return api_key, raw_key


def _created_response(api_key: ApiKey, raw_key: str) -> ApiKeyCreatedResponse:
    return ApiKeyCreatedResponse(**_api_key_response(api_key).model_dump(), key=raw_key)


def _api_key_response(api_key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=api_key.id,
        user_id=api_key.user_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scope=api_key.scope,
        is_active=api_key.is_active,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        provider_ids=sorted(link.provider_id for link in api_key.provider_links),
        model_ids=sorted(link.model_id for link in api_key.model_links),
    )


def _database_datetime(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _raise_api_key_not_found() -> NoReturn:
    raise_auth_error(status.HTTP_404_NOT_FOUND, "api_key_not_found", "API key not found")
