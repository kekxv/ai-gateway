from __future__ import annotations

from typing import Annotated, NoReturn

import orjson
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.admin.audit import log_multiplier_change
from ai_gateway.auth.dependencies import admin_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.catalog.schemas import (
    ProviderCreate,
    ProviderProtocolInput,
    ProviderProtocolResponse,
    ProviderResponse,
    ProviderUpdate,
)
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.security import decrypt_secret, encrypt_secret
from ai_gateway.db.models import (
    ApiKeyProvider,
    ModelRoute,
    Provider,
    ProviderProtocol,
    RequestLog,
    User,
)
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/admin/providers", tags=["admin-providers"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.post("", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: ProviderCreate,
    session: Session,
    _: AdminUser,
    settings: AppSettings,
) -> ProviderResponse:
    _validate_protocol_payloads(payload.protocols, creating=True)
    provider = Provider(
        name=payload.name,
        credential_encrypted=_encrypt_json(payload.credential, settings),
        enabled=payload.enabled,
        auto_load_models=payload.auto_load_models,
        model_sync_interval_seconds=(
            payload.model_sync_interval_seconds
            if payload.model_sync_interval_seconds is not None
            else settings.model_sync_interval_seconds
        ),
        cost_multiplier=payload.cost_multiplier,
        public_multiplier=payload.public_multiplier,
        protocols=[_new_protocol(item, settings) for item in payload.protocols],
    )
    session.add(provider)
    try:
        await session.flush()
        response = _provider_response(provider, settings)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        _raise_provider_conflict()
    return response


@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    session: Session,
    _: AdminUser,
    settings: AppSettings,
) -> list[ProviderResponse]:
    providers = (
        await session.scalars(
            select(Provider).options(selectinload(Provider.protocols)).order_by(Provider.id)
        )
    ).all()
    return [_provider_response(provider, settings) for provider in providers]


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: int,
    session: Session,
    _: AdminUser,
    settings: AppSettings,
) -> ProviderResponse:
    return _provider_response(await _get_provider(session, provider_id), settings)


@router.patch("/{provider_id}", response_model=ProviderResponse)
@router.put("/{provider_id}", response_model=ProviderResponse, include_in_schema=False)
async def update_provider(
    provider_id: int,
    payload: ProviderUpdate,
    session: Session,
    admin: AdminUser,
    settings: AppSettings,
) -> ProviderResponse:
    provider = await _get_provider(session, provider_id)
    old_cost_multiplier = provider.cost_multiplier
    old_public_multiplier = provider.public_multiplier
    if payload.name is not None:
        provider.name = payload.name
    if "credential" in payload.model_fields_set:
        if payload.credential is None:
            raise_auth_error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "credential_required",
                "Provider credentials cannot be cleared",
            )
        provider.credential_encrypted = _encrypt_json(payload.credential, settings)
    if payload.enabled is not None:
        provider.enabled = payload.enabled
    if payload.auto_load_models is not None:
        provider.auto_load_models = payload.auto_load_models
    if payload.model_sync_interval_seconds is not None:
        provider.model_sync_interval_seconds = payload.model_sync_interval_seconds
    if payload.protocols is not None:
        _validate_protocol_payloads(payload.protocols, creating=False)
        await _replace_protocols(session, provider, payload.protocols, settings)
    if payload.cost_multiplier is not None:
        provider.cost_multiplier = payload.cost_multiplier
        await log_multiplier_change(
            session=session,
            user_id=admin.id,
            resource_type="provider",
            resource_id=provider_id,
            old_value=old_cost_multiplier,
            new_value=payload.cost_multiplier,
            field_name="cost_multiplier",
        )
    if payload.public_multiplier is not None:
        provider.public_multiplier = payload.public_multiplier
        await log_multiplier_change(
            session=session,
            user_id=admin.id,
            resource_type="provider",
            resource_id=provider_id,
            old_value=old_public_multiplier,
            new_value=payload.public_multiplier,
            field_name="public_multiplier",
        )
    try:
        await session.flush()
        response = _provider_response(provider, settings)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        _raise_provider_conflict()
    return response


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(provider_id: int, session: Session, _: AdminUser) -> Response:
    await _get_provider(session, provider_id)
    route_ids = list(
        await session.scalars(select(ModelRoute.id).where(ModelRoute.provider_id == provider_id))
    )
    history_filter = RequestLog.provider_id == provider_id
    if route_ids:
        history_filter = or_(history_filter, RequestLog.model_route_id.in_(route_ids))
    history_id = await session.scalar(select(RequestLog.id).where(history_filter).limit(1))
    if history_id is not None:
        raise_auth_error(
            status.HTTP_409_CONFLICT,
            "provider_has_history",
            "Providers with request history must be disabled instead of deleted",
        )
    await session.execute(delete(ApiKeyProvider).where(ApiKeyProvider.provider_id == provider_id))
    await session.execute(delete(ModelRoute).where(ModelRoute.provider_id == provider_id))
    await session.execute(
        delete(ProviderProtocol).where(ProviderProtocol.provider_id == provider_id)
    )
    await session.execute(delete(Provider).where(Provider.id == provider_id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _get_provider(session: AsyncSession, provider_id: int) -> Provider:
    provider = await session.scalar(
        select(Provider).where(Provider.id == provider_id).options(selectinload(Provider.protocols))
    )
    if provider is None:
        raise_auth_error(
            status.HTTP_404_NOT_FOUND,
            "provider_not_found",
            "Provider not found",
        )
    return provider


async def _replace_protocols(
    session: AsyncSession,
    provider: Provider,
    payloads: list[ProviderProtocolInput],
    settings: Settings,
) -> None:
    existing_by_id = {protocol.id: protocol for protocol in provider.protocols}
    existing_by_key = {
        (protocol.protocol, protocol.base_url): protocol for protocol in provider.protocols
    }
    selected: list[ProviderProtocol] = []
    for payload in payloads:
        protocol = None
        if payload.id is not None:
            protocol = existing_by_id.get(payload.id)
            if protocol is None:
                raise_auth_error(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "invalid_provider_protocol",
                    "Provider protocol does not belong to this provider",
                )
        else:
            protocol = existing_by_key.get((payload.protocol, payload.base_url))
        if protocol is None:
            is_new = True
            protocol = ProviderProtocol(provider=provider)
        else:
            is_new = False
        protocol.protocol = payload.protocol
        protocol.base_url = payload.base_url
        protocol.websocket_url = payload.websocket_url
        protocol.supports_responses = payload.supports_responses
        if "extra_headers" in payload.model_fields_set:
            protocol.extra_headers_encrypted = (
                _encrypt_json(payload.extra_headers, settings)
                if payload.extra_headers is not None
                else None
            )
        elif is_new:
            protocol.extra_headers_encrypted = None
        protocol.enabled = payload.enabled
        selected.append(protocol)

    if not selected:
        route_id = await session.scalar(
            select(ModelRoute.id).where(ModelRoute.provider_id == provider.id).limit(1)
        )
        if route_id is not None:
            raise_auth_error(
                status.HTTP_409_CONFLICT,
                "provider_protocol_in_use",
                "Delete or reassign model routes before removing every provider protocol",
            )
    provider.protocols = selected


def _new_protocol(payload: ProviderProtocolInput, settings: Settings) -> ProviderProtocol:
    return ProviderProtocol(
        protocol=payload.protocol,
        base_url=payload.base_url,
        websocket_url=payload.websocket_url,
        supports_responses=payload.supports_responses,
        extra_headers_encrypted=(
            _encrypt_json(payload.extra_headers, settings)
            if payload.extra_headers is not None
            else None
        ),
        enabled=payload.enabled,
    )


def _validate_protocol_payloads(
    payloads: list[ProviderProtocolInput],
    *,
    creating: bool,
) -> None:
    keys = [(item.protocol, item.base_url) for item in payloads]
    ids = [item.id for item in payloads if item.id is not None]
    if len(keys) != len(set(keys)) or len(ids) != len(set(ids)):
        raise_auth_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "duplicate_provider_protocol",
            "Protocol and base URL combinations must be unique per provider",
        )
    if creating and ids:
        raise_auth_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_provider_protocol",
            "Provider protocol IDs cannot be supplied when creating a provider",
        )


def _provider_response(provider: Provider, settings: Settings) -> ProviderResponse:
    protocols = sorted(provider.protocols, key=lambda item: item.id)
    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        has_credential=orjson.loads(
            decrypt_secret(provider.credential_encrypted, settings=settings)
        )
        != {},
        enabled=provider.enabled,
        auto_load_models=provider.auto_load_models,
        model_sync_interval_seconds=provider.model_sync_interval_seconds,
        last_model_sync_at=provider.last_model_sync_at,
        protocols=[
            ProviderProtocolResponse(
                id=protocol.id,
                protocol=protocol.protocol,
                base_url=protocol.base_url,
                websocket_url=protocol.websocket_url,
                has_extra_headers=protocol.extra_headers_encrypted is not None,
                supports_responses=protocol.supports_responses,
                enabled=protocol.enabled,
            )
            for protocol in protocols
        ],
        cost_multiplier=provider.cost_multiplier,
        public_multiplier=provider.public_multiplier,
    )


def _encrypt_json(value: object, settings: Settings) -> bytes:
    canonical_json = orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
    return encrypt_secret(canonical_json.decode(), settings=settings)


def _raise_provider_conflict() -> NoReturn:
    raise_auth_error(
        status.HTTP_409_CONFLICT,
        "provider_conflict",
        "Provider name and protocol configurations must be unique",
    )
