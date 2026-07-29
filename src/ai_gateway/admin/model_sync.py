from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from typing import Protocol as TypingProtocol

import httpx
import orjson
from fastapi import APIRouter, Body, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.audit.redaction import redact_json
from ai_gateway.auth.dependencies import admin_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.catalog.discovery import discover_models, discovery_url
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol, RouteSource
from ai_gateway.core.logging import sanitize_log_event
from ai_gateway.db.models import Model, ModelAlias, ModelRoute, Provider, ProviderProtocol, User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/admin/providers", tags=["admin-providers"])
logger = logging.getLogger("uvicorn")

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Clock = Callable[[], datetime]
_SYNC_WRITE_ATTEMPTS = 3
_MAX_UPSTREAM_ERROR_CHARS = 2048


class HttpClientProvider(TypingProtocol):
    async def client_for(self, url: str | httpx.URL) -> httpx.AsyncClient: ...


@dataclass(frozen=True, slots=True)
class ModelSyncResult:
    provider_id: int
    discovered_models: int
    created_models: int
    created_routes: int
    updated_routes: int
    disabled_routes: int


class SyncProviderNotFoundError(LookupError):
    pass


class DiscoverModelsRequest(BaseModel):
    models: list[str] | None = Field(
        default=None,
        description="Only sync these models. If null/empty, sync all discovered models.",
    )


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.get("/{provider_id}/discover-models")
async def discover_provider_models_endpoint(
    provider_id: int,
    request: Request,
    session: Session,
    _: AdminUser,
    settings: AppSettings,
) -> dict[str, list[str]]:
    """Discover available models from the provider without writing to the database."""
    http_client_factory = getattr(request.app.state, "http_client_factory", None)
    if http_client_factory is None:
        raise_auth_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "model_discovery_unavailable",
            "Model discovery is unavailable",
        )
    try:
        models_by_protocol = await discover_provider_models(
            provider_id,
            session=session,
            http_client_factory=http_client_factory,
            settings=settings,
        )
        return models_by_protocol
    except SyncProviderNotFoundError:
        raise_auth_error(
            status.HTTP_404_NOT_FOUND,
            "provider_not_found",
            "Provider not found",
        )
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        logger.warning(
            "Provider model discovery failed for provider_id=%d: %s: %s",
            provider_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        raise_auth_error(
            status.HTTP_502_BAD_GATEWAY,
            "model_discovery_failed",
            _model_discovery_error_message(exc),
        )


@router.post("/{provider_id}/sync-models", response_model=ModelSyncResult)
async def sync_provider_models_endpoint(
    provider_id: int,
    request: Request,
    session: Session,
    _: AdminUser,
    settings: AppSettings,
    body: DiscoverModelsRequest = Body(default=None),
) -> ModelSyncResult:
    http_client_factory = getattr(request.app.state, "http_client_factory", None)
    if http_client_factory is None:
        raise_auth_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "model_discovery_unavailable",
            "Model discovery is unavailable",
        )
    selected_models = body.models if body is not None else None
    try:
        return await sync_provider_models(
            provider_id,
            session=session,
            http_client_factory=http_client_factory,
            settings=settings,
            selected_models=selected_models,
        )
    except SyncProviderNotFoundError:
        raise_auth_error(
            status.HTTP_404_NOT_FOUND,
            "provider_not_found",
            "Provider not found",
        )
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        logger.warning(
            "Provider model sync failed for provider_id=%d: %s: %s",
            provider_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        raise_auth_error(
            status.HTTP_502_BAD_GATEWAY,
            "model_discovery_failed",
            _model_discovery_error_message(exc),
        )


async def discover_provider_models(
    provider_id: int,
    *,
    session: AsyncSession,
    http_client_factory: HttpClientProvider,
    settings: Settings,
) -> dict[str, list[str]]:
    """Discover models through the preferred enabled provider protocol."""
    provider = await session.scalar(
        select(Provider).where(Provider.id == provider_id).options(selectinload(Provider.protocols))
    )
    if provider is None:
        raise SyncProviderNotFoundError(provider_id)

    provider_protocol = _preferred_discovery_protocol(provider.protocols)
    if provider_protocol is None:
        return {}
    url = discovery_url(provider_protocol)
    client = await http_client_factory.client_for(url)
    models = await discover_models(
        provider_protocol,
        client=client,
        settings=settings,
    )
    return {provider_protocol.protocol.value: models}


async def sync_provider_models(
    provider_id: int,
    *,
    session: AsyncSession,
    http_client_factory: HttpClientProvider,
    settings: Settings,
    clock: Clock = _utcnow,
    selected_models: list[str] | None = None,
) -> ModelSyncResult:
    """Synchronize one provider through its preferred discovery protocol.

    If selected_models is provided, only sync those specific models.
    """

    provider = await session.scalar(
        select(Provider).where(Provider.id == provider_id).options(selectinload(Provider.protocols))
    )
    if provider is None:
        raise SyncProviderNotFoundError(provider_id)

    discovered_by_protocol: dict[int, list[str]] = {}
    provider_protocol = _preferred_discovery_protocol(provider.protocols)
    if provider_protocol is not None:
        url = discovery_url(provider_protocol)
        client = await http_client_factory.client_for(url)
        discovered = await discover_models(
            provider_protocol,
            client=client,
            settings=settings,
        )
        # Filter to selected models if specified
        if selected_models:
            discovered = [m for m in discovered if m in selected_models]
        discovered_by_protocol[provider_protocol.id] = discovered

    for attempt in range(_SYNC_WRITE_ATTEMPTS):
        try:
            return await _apply_discovered_models(
                provider_id,
                discovered_by_protocol=discovered_by_protocol,
                session=session,
                clock=clock,
                selected_models=selected_models,
            )
        except IntegrityError:
            await session.rollback()
            if attempt == _SYNC_WRITE_ATTEMPTS - 1:
                raise
    raise AssertionError("unreachable")


def _preferred_discovery_protocol(
    provider_protocols: list[ProviderProtocol],
) -> ProviderProtocol | None:
    enabled_protocols = [protocol for protocol in provider_protocols if protocol.enabled]
    if not enabled_protocols:
        return None
    return min(
        enabled_protocols,
        key=lambda protocol: (protocol.protocol is not Protocol.OPENAI, protocol.id),
    )


def _model_discovery_error_message(exc: httpx.HTTPError | ValueError | RuntimeError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        status_label = f"{response.status_code} {response.reason_phrase}".strip()
        message = f"Upstream provider returned {status_label}"
        detail = _upstream_error_detail(response)
        if detail:
            message = f"{message}: {detail}"
    else:
        detail = sanitize_log_event(exc).strip()
        message = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
    return _truncate_upstream_error(message)


def _upstream_error_detail(response: httpx.Response) -> str:
    try:
        detail = orjson.dumps(redact_json(response.json())).decode()
    except ValueError:
        detail = response.text.strip()
    return sanitize_log_event(detail)


def _truncate_upstream_error(message: str) -> str:
    if len(message) <= _MAX_UPSTREAM_ERROR_CHARS:
        return message
    return f"{message[: _MAX_UPSTREAM_ERROR_CHARS - 1]}…"


async def _apply_discovered_models(
    provider_id: int,
    *,
    discovered_by_protocol: dict[int, list[str]],
    session: AsyncSession,
    clock: Clock,
    selected_models: list[str] | None = None,
) -> ModelSyncResult:
    provider = await session.get(Provider, provider_id)
    if provider is None:
        raise SyncProviderNotFoundError(provider_id)

    all_names = {
        name for discovered_names in discovered_by_protocol.values() for name in discovered_names
    }
    models_by_name = await _models_by_discovered_name(session, all_names)
    created_models = 0
    for name in sorted(all_names):
        if name not in models_by_name:
            model = Model(canonical_name=name, display_name=name)
            session.add(model)
            models_by_name[name] = model
            created_models += 1
    if created_models:
        await session.flush()

    protocol_ids = set(discovered_by_protocol)
    existing_routes = (
        list(
            await session.scalars(
                select(ModelRoute).where(
                    ModelRoute.provider_id == provider_id,
                    ModelRoute.provider_protocol_id.in_(protocol_ids),
                )
            )
        )
        if protocol_ids
        else []
    )
    routes_by_key = {
        (route.provider_protocol_id, route.model_id): route for route in existing_routes
    }
    seen_route_keys: set[tuple[int, int]] = set()
    created_routes = 0
    updated_routes = 0

    for protocol_id, discovered_names in discovered_by_protocol.items():
        for upstream_name in discovered_names:
            model = models_by_name[upstream_name]
            key = (protocol_id, model.id)
            if key in seen_route_keys:
                continue
            seen_route_keys.add(key)
            route = routes_by_key.get(key)
            if route is None:
                route = ModelRoute(
                    model_id=model.id,
                    provider_id=provider_id,
                    provider_protocol_id=protocol_id,
                    upstream_model=upstream_name,
                    enabled=True,
                    source=RouteSource.DISCOVERED,
                )
                session.add(route)
                routes_by_key[key] = route
                created_routes += 1
            elif route.source is RouteSource.DISCOVERED:
                if route.upstream_model != upstream_name or not route.enabled:
                    updated_routes += 1
                route.upstream_model = upstream_name
                route.enabled = True

    disabled_routes = 0
    # Only disable routes for models that were discovered but not selected
    # If selected_models is provided, don't disable existing routes for non-selected models
    if selected_models is None:
        for route in existing_routes:
            key = (route.provider_protocol_id, route.model_id)
            if (
                route.source is RouteSource.DISCOVERED
                and key not in seen_route_keys
                and route.enabled
            ):
                route.enabled = False
                disabled_routes += 1

    provider.last_model_sync_at = clock()
    await session.commit()
    return ModelSyncResult(
        provider_id=provider_id,
        discovered_models=len(all_names),
        created_models=created_models,
        created_routes=created_routes,
        updated_routes=updated_routes,
        disabled_routes=disabled_routes,
    )


async def _models_by_discovered_name(
    session: AsyncSession,
    names: set[str],
) -> dict[str, Model]:
    if not names:
        return {}
    canonical_models = list(
        await session.scalars(select(Model).where(Model.canonical_name.in_(names)))
    )
    models_by_name = {model.canonical_name: model for model in canonical_models}
    aliases = list(
        await session.scalars(
            select(ModelAlias)
            .where(ModelAlias.alias.in_(names))
            .options(selectinload(ModelAlias.model))
        )
    )
    for alias in aliases:
        models_by_name.setdefault(alias.alias, alias.model)
    return models_by_name
