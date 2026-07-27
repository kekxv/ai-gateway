from __future__ import annotations

import json
from decimal import Decimal
from typing import Annotated, Literal, cast

import orjson
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.auth.dependencies import admin_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.catalog.schemas import (
    BaseUrl,
    CatalogName,
    Price,
    PriceMultiplier,
    ProviderCredentialObject,
    RoutingStrategy,
    WebsocketUrl,
)
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol, RouteRuntimeState, RouteSource
from ai_gateway.core.security import decrypt_secret, encrypt_secret
from ai_gateway.db.models import Model, ModelAlias, ModelRoute, Provider, ProviderProtocol, User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/admin/configuration", tags=["admin-configuration"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
AppSettings = Annotated[Settings, Depends(get_settings)]
JsonObject = dict[str, JsonValue]


class CatalogProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: Protocol
    base_url: BaseUrl
    websocket_url: WebsocketUrl | None = None
    extra_headers: JsonObject | None = None
    supports_responses: bool = True
    enabled: bool = True


class CatalogProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CatalogName
    credential: ProviderCredentialObject | None = None
    enabled: bool = True
    auto_load_models: bool = False
    model_sync_interval_seconds: int = Field(ge=1)
    price_multiplier: PriceMultiplier = Decimal("1.00")
    protocols: list[CatalogProtocol] = Field(default_factory=list)


class CatalogAlias(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: CatalogName
    enabled: bool = True


class CatalogRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: CatalogName
    protocol: Protocol
    base_url: BaseUrl
    upstream_model: CatalogName
    weight: int = Field(ge=1, le=10000)
    enabled: bool = True


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_name: CatalogName
    display_name: CatalogName
    input_price_per_million: Price = Decimal("0")
    output_price_per_million: Price = Decimal("0")
    cache_read_price_per_million: Price = Decimal("0")
    cache_write_price_per_million: Price = Decimal("0")
    price_multiplier: PriceMultiplier = Decimal("1.00")
    enabled: bool = True
    routing_strategy: RoutingStrategy = "weighted_random"
    aliases: list[CatalogAlias] = Field(default_factory=list)
    routes: list[CatalogRoute] = Field(default_factory=list)


class CatalogBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["ai-gateway.catalog"]
    version: Literal[1]
    providers: list[CatalogProvider] = Field(default_factory=list)
    models: list[CatalogModel] = Field(default_factory=list)


class CatalogImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers_created: int
    providers_updated: int
    models_created: int
    models_updated: int
    routes_created: int
    routes_updated: int


async def export_catalog_bundle(
    session: AsyncSession,
    settings: Settings,
    include_secrets: bool,
) -> CatalogBundle:
    providers = (
        await session.scalars(
            select(Provider).options(selectinload(Provider.protocols)).order_by(Provider.name)
        )
    ).all()
    models = (
        await session.scalars(
            select(Model)
            .options(
                selectinload(Model.aliases),
                selectinload(Model.routes).selectinload(ModelRoute.provider),
                selectinload(Model.routes).selectinload(ModelRoute.provider_protocol),
            )
            .order_by(Model.canonical_name)
        )
    ).all()
    return CatalogBundle(
        format="ai-gateway.catalog",
        version=1,
        providers=[
            _catalog_provider(provider, settings, include_secrets) for provider in providers
        ],
        models=[_catalog_model(model) for model in models],
    )


@router.get("/export")
async def export_configuration(
    session: Session,
    _: AdminUser,
    settings: AppSettings,
    include_secrets: bool = False,
) -> Response:
    bundle = await export_catalog_bundle(session, settings, include_secrets)
    return Response(
        content=orjson.dumps(_exact_json_numbers(bundle.model_dump())),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="ai-gateway-catalog-v1.json"'},
    )


@router.post("/import", response_model=CatalogImportResult)
async def import_configuration(
    request: Request,
    session: Session,
    _: AdminUser,
    settings: AppSettings,
) -> CatalogImportResult:
    bundle = await _catalog_bundle_from_request(request)
    return await import_catalog_bundle(session, settings, bundle)


async def import_catalog_bundle(
    session: AsyncSession,
    settings: Settings,
    bundle: CatalogBundle,
) -> CatalogImportResult:
    try:
        async with session.begin_nested():
            await _validate_import_bundle(session, bundle)
            result = await _merge_catalog_bundle(session, settings, bundle)
            await session.flush()
        await session.commit()
    except IntegrityError:
        await session.rollback()
        _raise_catalog_import_conflict()
    return result


async def _validate_import_bundle(session: AsyncSession, bundle: CatalogBundle) -> None:
    provider_names = [provider.name for provider in bundle.providers]
    model_names = [model.canonical_name for model in bundle.models]
    if len(provider_names) != len(set(provider_names)) or len(model_names) != len(set(model_names)):
        _raise_catalog_import_validation(
            "Provider and model names must be unique in a catalog bundle"
        )

    protocol_keys: set[tuple[str, Protocol, str]] = set()
    for provider in bundle.providers:
        for protocol in provider.protocols:
            key = (provider.name, protocol.protocol, protocol.base_url)
            if key in protocol_keys:
                _raise_catalog_import_validation("Provider protocol references must be unique")
            protocol_keys.add(key)

    aliases: dict[str, str] = {}
    for model in bundle.models:
        for alias in model.aliases:
            existing_owner = aliases.get(alias.alias)
            if existing_owner == model.canonical_name:
                _raise_catalog_import_validation("Model aliases must be unique")
            if existing_owner is not None or alias.alias == model.canonical_name:
                _raise_catalog_import_conflict()
            if alias.alias in model_names and alias.alias != model.canonical_name:
                _raise_catalog_import_conflict()
            aliases[alias.alias] = model.canonical_name

    route_provider_names = {route.provider for model in bundle.models for route in model.routes}
    existing_protocols = set(
        (
            provider.name,
            protocol.protocol,
            protocol.base_url,
        )
        for provider in (
            await session.scalars(
                select(Provider)
                .options(selectinload(Provider.protocols))
                .where(Provider.name.in_(route_provider_names))
            )
        ).all()
        for protocol in provider.protocols
    )
    for model in bundle.models:
        route_keys: set[tuple[str, Protocol, str]] = set()
        for route in model.routes:
            key = (route.provider, route.protocol, route.base_url)
            if key in route_keys:
                _raise_catalog_import_conflict()
            route_keys.add(key)
            if key not in protocol_keys and key not in existing_protocols:
                _raise_catalog_import_validation(
                    "Each imported route must reference an existing or imported provider protocol"
                )

    if not aliases and not model_names:
        return
    existing_models = {
        model.canonical_name: model.id
        for model in (
            await session.scalars(select(Model).where(Model.canonical_name.in_(set(model_names))))
        ).all()
    }
    conflicting_canonical_names = set(
        await session.scalars(
            select(Model.canonical_name).where(Model.canonical_name.in_(set(aliases)))
        )
    )
    if conflicting_canonical_names:
        _raise_catalog_import_conflict()
    conflicting_aliases = (
        await session.scalars(
            select(ModelAlias).where(ModelAlias.alias.in_(set(aliases) | set(model_names)))
        )
    ).all()
    for stored_alias in conflicting_aliases:
        target_model = aliases.get(stored_alias.alias)
        if target_model is None or existing_models.get(target_model) != stored_alias.model_id:
            _raise_catalog_import_conflict()


async def _merge_catalog_bundle(
    session: AsyncSession,
    settings: Settings,
    bundle: CatalogBundle,
) -> CatalogImportResult:
    providers = {
        provider.name: provider
        for provider in (
            await session.scalars(
                select(Provider)
                .options(selectinload(Provider.protocols))
                .where(Provider.name.in_([item.name for item in bundle.providers]))
            )
        ).all()
    }
    providers_created = 0
    providers_updated = 0
    protocols: dict[tuple[str, Protocol, str], ProviderProtocol] = {}
    for provider_payload in bundle.providers:
        provider = providers.get(provider_payload.name)
        if provider is None:
            provider = Provider(
                name=provider_payload.name,
                credential_encrypted=_encrypt_json(provider_payload.credential or {}, settings),
            )
            session.add(provider)
            providers[provider_payload.name] = provider
            providers_created += 1
        else:
            providers_updated += 1
            if provider_payload.credential is not None:
                provider.credential_encrypted = _encrypt_json(provider_payload.credential, settings)
        provider.enabled = provider_payload.enabled
        provider.auto_load_models = provider_payload.auto_load_models
        provider.model_sync_interval_seconds = provider_payload.model_sync_interval_seconds
        provider.price_multiplier = provider_payload.price_multiplier
        known_protocols = {(item.protocol, item.base_url): item for item in provider.protocols}
        for protocol_payload in provider_payload.protocols:
            key = (protocol_payload.protocol, protocol_payload.base_url)
            protocol = known_protocols.get(key)
            if protocol is None:
                protocol = ProviderProtocol(
                    protocol=protocol_payload.protocol,
                    base_url=protocol_payload.base_url,
                    extra_headers_encrypted=(
                        _encrypt_json(protocol_payload.extra_headers, settings)
                        if protocol_payload.extra_headers is not None
                        else None
                    ),
                )
                provider.protocols.append(protocol)
                known_protocols[key] = protocol
            elif protocol_payload.extra_headers is not None:
                protocol.extra_headers_encrypted = _encrypt_json(
                    protocol_payload.extra_headers,
                    settings,
                )
            protocol.websocket_url = protocol_payload.websocket_url
            protocol.supports_responses = protocol_payload.supports_responses
            protocol.enabled = protocol_payload.enabled
            protocols[(provider.name, protocol.protocol, protocol.base_url)] = protocol
    await session.flush()

    referenced_protocol_keys = {
        (route.provider, route.protocol, route.base_url)
        for model in bundle.models
        for route in model.routes
    }
    missing_protocol_keys = referenced_protocol_keys - set(protocols)
    if missing_protocol_keys:
        for provider in (
            await session.scalars(
                select(Provider)
                .options(selectinload(Provider.protocols))
                .where(Provider.name.in_({key[0] for key in missing_protocol_keys}))
            )
        ).all():
            for protocol in provider.protocols:
                protocols[(provider.name, protocol.protocol, protocol.base_url)] = protocol

    models = {
        model.canonical_name: model
        for model in (
            await session.scalars(
                select(Model)
                .options(selectinload(Model.aliases))
                .where(Model.canonical_name.in_([item.canonical_name for item in bundle.models]))
            )
        ).all()
    }
    models_created = 0
    models_updated = 0
    for model_payload in bundle.models:
        model = models.get(model_payload.canonical_name)
        if model is None:
            model = Model(
                canonical_name=model_payload.canonical_name,
                display_name=model_payload.display_name,
            )
            session.add(model)
            models[model_payload.canonical_name] = model
            models_created += 1
        else:
            models_updated += 1
        model.display_name = model_payload.display_name
        model.input_price_per_million = model_payload.input_price_per_million
        model.output_price_per_million = model_payload.output_price_per_million
        model.cache_read_price_per_million = model_payload.cache_read_price_per_million
        model.cache_write_price_per_million = model_payload.cache_write_price_per_million
        model.price_multiplier = model_payload.price_multiplier
        model.enabled = model_payload.enabled
        model.routing_strategy = model_payload.routing_strategy
        aliases = {alias.alias: alias for alias in model.aliases}
        for alias_payload in model_payload.aliases:
            alias = aliases.get(alias_payload.alias)
            if alias is None:
                alias = ModelAlias(alias=alias_payload.alias, enabled=alias_payload.enabled)
                model.aliases.append(alias)
                aliases[alias.alias] = alias
            else:
                alias.enabled = alias_payload.enabled
    await session.flush()

    routes_created = 0
    routes_updated = 0
    for model_payload in bundle.models:
        model = models[model_payload.canonical_name]
        for route_payload in model_payload.routes:
            protocol = protocols[
                (
                    route_payload.provider,
                    route_payload.protocol,
                    route_payload.base_url,
                )
            ]
            route = await session.scalar(
                select(ModelRoute).where(
                    ModelRoute.model_id == model.id,
                    ModelRoute.provider_id == protocol.provider_id,
                    ModelRoute.provider_protocol_id == protocol.id,
                )
            )
            if route is None:
                route = ModelRoute(
                    model_id=model.id,
                    provider_id=protocol.provider_id,
                    provider_protocol_id=protocol.id,
                    upstream_model=route_payload.upstream_model,
                    weight=route_payload.weight,
                    enabled=route_payload.enabled,
                    source=RouteSource.MANUAL,
                    runtime_state=RouteRuntimeState.CLOSED,
                    consecutive_failures=0,
                    disabled_until=None,
                    last_error_code=None,
                    last_error_at=None,
                )
                session.add(route)
                routes_created += 1
            else:
                routes_updated += 1
                route.upstream_model = route_payload.upstream_model
                route.weight = route_payload.weight
                route.enabled = route_payload.enabled

    return CatalogImportResult(
        providers_created=providers_created,
        providers_updated=providers_updated,
        models_created=models_created,
        models_updated=models_updated,
        routes_created=routes_created,
        routes_updated=routes_updated,
    )


async def _catalog_bundle_from_request(request: Request) -> CatalogBundle:
    try:
        payload = json.loads(await request.body(), parse_float=Decimal)
        return CatalogBundle.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        errors = exc.errors() if isinstance(exc, ValidationError) else []
        raise RequestValidationError(errors) from exc


def _exact_json_numbers(value: object) -> object:
    if isinstance(value, Decimal):
        return orjson.Fragment(format(value, "f"))
    if isinstance(value, dict):
        return {key: _exact_json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_exact_json_numbers(item) for item in value]
    return value


def _encrypt_json(value: object, settings: Settings) -> bytes:
    return encrypt_secret(
        orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode(),
        settings=settings,
    )


def _raise_catalog_import_validation(message: str) -> None:
    raise_auth_error(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "catalog_import_invalid",
        message,
    )


def _raise_catalog_import_conflict() -> None:
    raise_auth_error(
        status.HTTP_409_CONFLICT,
        "catalog_import_conflict",
        "The catalog bundle conflicts with existing provider, model, alias, or route names",
    )


def _catalog_provider(
    provider: Provider,
    settings: Settings,
    include_secrets: bool,
) -> CatalogProvider:
    return CatalogProvider(
        name=provider.name,
        credential=(
            orjson.loads(decrypt_secret(provider.credential_encrypted, settings=settings))
            if include_secrets
            else None
        ),
        enabled=provider.enabled,
        auto_load_models=provider.auto_load_models,
        model_sync_interval_seconds=provider.model_sync_interval_seconds,
        price_multiplier=provider.price_multiplier,
        protocols=[
            CatalogProtocol(
                protocol=protocol.protocol,
                base_url=protocol.base_url,
                websocket_url=protocol.websocket_url,
                extra_headers=(
                    orjson.loads(
                        decrypt_secret(protocol.extra_headers_encrypted, settings=settings)
                    )
                    if include_secrets and protocol.extra_headers_encrypted is not None
                    else None
                ),
                supports_responses=protocol.supports_responses,
                enabled=protocol.enabled,
            )
            for protocol in sorted(
                provider.protocols,
                key=lambda item: (item.protocol.value, item.base_url),
            )
        ],
    )


def _catalog_model(model: Model) -> CatalogModel:
    return CatalogModel(
        canonical_name=model.canonical_name,
        display_name=model.display_name,
        input_price_per_million=model.input_price_per_million,
        output_price_per_million=model.output_price_per_million,
        cache_read_price_per_million=model.cache_read_price_per_million,
        cache_write_price_per_million=model.cache_write_price_per_million,
        price_multiplier=model.price_multiplier,
        enabled=model.enabled,
        routing_strategy=cast(RoutingStrategy, model.routing_strategy),
        aliases=[
            CatalogAlias(alias=alias.alias, enabled=alias.enabled)
            for alias in sorted(model.aliases, key=lambda item: item.alias)
        ],
        routes=[
            CatalogRoute(
                provider=route.provider.name,
                protocol=route.provider_protocol.protocol,
                base_url=route.provider_protocol.base_url,
                upstream_model=route.upstream_model,
                weight=route.weight,
                enabled=route.enabled,
            )
            for route in sorted(
                model.routes,
                key=lambda item: (
                    item.provider.name,
                    item.provider_protocol.protocol.value,
                    item.provider_protocol.base_url,
                ),
            )
        ],
    )
