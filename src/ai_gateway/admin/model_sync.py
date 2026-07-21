from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from typing import Protocol as TypingProtocol

import httpx
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.auth.dependencies import admin_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.catalog.discovery import discover_models, discovery_url
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import RouteSource
from ai_gateway.db.models import Model, ModelAlias, ModelRoute, Provider, User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/admin/providers", tags=["admin-providers"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Clock = Callable[[], datetime]


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


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.post("/{provider_id}/sync-models", response_model=ModelSyncResult)
async def sync_provider_models_endpoint(
    provider_id: int,
    request: Request,
    session: Session,
    _: AdminUser,
    settings: AppSettings,
) -> ModelSyncResult:
    http_client_factory = getattr(request.app.state, "http_client_factory", None)
    if http_client_factory is None:
        raise_auth_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "model_discovery_unavailable",
            "Model discovery is unavailable",
        )
    try:
        return await sync_provider_models(
            provider_id,
            session=session,
            http_client_factory=http_client_factory,
            settings=settings,
        )
    except SyncProviderNotFoundError:
        raise_auth_error(
            status.HTTP_404_NOT_FOUND,
            "provider_not_found",
            "Provider not found",
        )
    except (httpx.HTTPError, ValueError, RuntimeError):
        raise_auth_error(
            status.HTTP_502_BAD_GATEWAY,
            "model_discovery_failed",
            "Provider model discovery failed",
        )


async def sync_provider_models(
    provider_id: int,
    *,
    session: AsyncSession,
    http_client_factory: HttpClientProvider,
    settings: Settings,
    clock: Clock = _utcnow,
) -> ModelSyncResult:
    """Synchronize one provider after every enabled protocol discovers successfully."""

    provider = await session.scalar(
        select(Provider).where(Provider.id == provider_id).options(selectinload(Provider.protocols))
    )
    if provider is None:
        raise SyncProviderNotFoundError(provider_id)

    enabled_protocols = [protocol for protocol in provider.protocols if protocol.enabled]
    discovered_by_protocol: dict[int, list[str]] = {}
    for provider_protocol in enabled_protocols:
        url = discovery_url(provider_protocol)
        client = await http_client_factory.client_for(url)
        discovered_by_protocol[provider_protocol.id] = await discover_models(
            provider_protocol,
            client=client,
            settings=settings,
        )

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
    for route in existing_routes:
        key = (route.provider_protocol_id, route.model_id)
        if route.source is RouteSource.DISCOVERED and key not in seen_route_keys and route.enabled:
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
