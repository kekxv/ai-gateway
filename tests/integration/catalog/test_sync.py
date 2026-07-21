from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import orjson
import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from ai_gateway.admin.model_sync import sync_provider_models
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol, RouteSource
from ai_gateway.core.security import encrypt_secret, hash_password, issue_access_token
from ai_gateway.db.models import (
    Account,
    Model,
    ModelAlias,
    ModelRoute,
    Provider,
    ProviderProtocol,
    User,
)
from ai_gateway.db.session import get_session
from ai_gateway.main import create_app


class FakeHttpClientFactory:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.urls: list[str] = []

    async def client_for(self, url: str | httpx.URL) -> httpx.AsyncClient:
        self.urls.append(str(url))
        return self.client


@pytest.fixture
def sync_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret="model-sync-integration-jwt-secret",
        encryption_key=Fernet.generate_key().decode(),
    )


def _encrypted_json(value: dict[str, str], settings: Settings) -> bytes:
    return encrypt_secret(orjson.dumps(value).decode(), settings=settings)


def _provider(
    settings: Settings,
    *,
    name: str,
    protocols: tuple[Protocol, ...] = (Protocol.OPENAI,),
    enabled: bool = True,
    auto_load_models: bool = True,
) -> Provider:
    return Provider(
        name=name,
        credential_encrypted=_encrypted_json({"api_key": "sync-secret"}, settings),
        enabled=enabled,
        auto_load_models=auto_load_models,
        model_sync_interval_seconds=60,
        protocols=[
            ProviderProtocol(
                protocol=protocol,
                base_url=f"https://{protocol.value}.example/v1"
                if protocol is Protocol.OPENAI
                else f"https://{protocol.value}.example",
                enabled=True,
            )
            for protocol in protocols
        ],
    )


def _json_response(request: httpx.Request, payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json=payload, request=request)


@pytest.mark.asyncio
async def test_sync_is_idempotent_preserves_aliases_and_never_mutates_manual_routes(
    session: AsyncSession,
    sync_settings: Settings,
) -> None:
    provider = _provider(sync_settings, name="sync-idempotent")
    protocol = provider.protocols[0]
    alias_model = Model(
        canonical_name="alias-target",
        display_name="Alias Target",
        aliases=[ModelAlias(alias="alias-native")],
    )
    found_model = Model(canonical_name="native-found", display_name="Found")
    missing_model = Model(canonical_name="native-missing", display_name="Missing")
    manual_model = Model(canonical_name="manual-model", display_name="Manual")
    provider.routes.extend(
        [
            ModelRoute(
                model=found_model,
                provider_protocol=protocol,
                upstream_model="stale-upstream-name",
                enabled=False,
                source=RouteSource.DISCOVERED,
            ),
            ModelRoute(
                model=missing_model,
                provider_protocol=protocol,
                upstream_model="native-missing",
                enabled=True,
                source=RouteSource.DISCOVERED,
            ),
            ModelRoute(
                model=manual_model,
                provider_protocol=protocol,
                upstream_model="manual-upstream",
                enabled=True,
                source=RouteSource.MANUAL,
            ),
        ]
    )
    session.add_all([provider, alias_model])
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return _json_response(
            request,
            {
                "data": [
                    {"id": "native-found"},
                    {"id": "alias-native"},
                    {"id": "native-new"},
                ],
                "has_more": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        factory = FakeHttpClientFactory(client)
        first = await sync_provider_models(
            provider.id,
            session=session,
            http_client_factory=factory,
            settings=sync_settings,
        )
        second = await sync_provider_models(
            provider.id,
            session=session,
            http_client_factory=factory,
            settings=sync_settings,
        )

    models = list(
        await session.scalars(
            select(Model).options(selectinload(Model.aliases)).order_by(Model.canonical_name)
        )
    )
    routes = list(
        await session.scalars(
            select(ModelRoute)
            .where(ModelRoute.provider_id == provider.id)
            .order_by(ModelRoute.upstream_model)
        )
    )
    model_names = [model.canonical_name for model in models]
    routes_by_model = {route.model.canonical_name: route for route in routes}

    assert first.discovered_models == 3
    assert second.discovered_models == 3
    assert model_names.count("native-new") == 1
    assert [alias.alias for alias in alias_model.aliases] == ["alias-native"]
    assert routes_by_model["alias-target"].upstream_model == "alias-native"
    assert routes_by_model["alias-target"].source is RouteSource.DISCOVERED
    assert routes_by_model["native-found"].upstream_model == "native-found"
    assert routes_by_model["native-found"].enabled is True
    assert routes_by_model["native-missing"].enabled is False
    assert routes_by_model["manual-model"].upstream_model == "manual-upstream"
    assert routes_by_model["manual-model"].enabled is True
    assert routes_by_model["manual-model"].source is RouteSource.MANUAL
    assert provider.last_model_sync_at is not None
    assert len(factory.urls) == 2


@pytest.mark.asyncio
async def test_failed_multi_protocol_discovery_does_not_apply_partial_catalog_changes(
    session: AsyncSession,
    sync_settings: Settings,
) -> None:
    provider = _provider(
        sync_settings,
        name="sync-atomic-failure",
        protocols=(Protocol.OPENAI, Protocol.CLAUDE),
    )
    stale_model = Model(canonical_name="stale-discovered", display_name="Stale")
    provider.routes.append(
        ModelRoute(
            model=stale_model,
            provider_protocol=provider.protocols[0],
            upstream_model="stale-discovered",
            source=RouteSource.DISCOVERED,
            enabled=True,
        )
    )
    session.add(provider)
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openai.example":
            return _json_response(
                request,
                {"data": [{"id": "must-not-be-created"}], "has_more": False},
            )
        return httpx.Response(503, json={"error": "temporary"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await sync_provider_models(
                provider.id,
                session=session,
                http_client_factory=FakeHttpClientFactory(client),
                settings=sync_settings,
            )

    assert (
        await session.scalar(select(Model.id).where(Model.canonical_name == "must-not-be-created"))
        is None
    )
    assert provider.routes[0].enabled is True
    assert provider.last_model_sync_at is None


@pytest.mark.asyncio
async def test_sync_endpoint_uses_app_owned_http_factory(
    session: AsyncSession,
    sync_settings: Settings,
) -> None:
    provider = _provider(sync_settings, name="sync-endpoint")
    admin = User(
        email="sync-admin@example.com",
        password_hash=hash_password("sync-admin-password"),
        role="admin",
        account=Account(),
    )
    session.add_all([provider, admin])
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            request,
            {"data": [{"id": "endpoint-model"}], "has_more": False},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream_client:
        factory = FakeHttpClientFactory(upstream_client)
        app = create_app(sync_settings)
        app.state.http_client_factory = factory

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_settings] = lambda: sync_settings
        token = issue_access_token(user_id=admin.id, settings=sync_settings)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"authorization": f"Bearer {token}"},
        ) as client:
            response = await client.post(f"/admin/providers/{provider.id}/sync-models")

    assert response.status_code == 200, response.text
    assert response.json()["provider_id"] == provider.id
    assert response.json()["discovered_models"] == 1
    assert factory.urls == ["https://openai.example/v1/models"]


@pytest.mark.asyncio
async def test_two_schedulers_use_mysql_lock_to_run_only_one_sync(
    test_engine: AsyncEngine,
    sync_settings: Settings,
) -> None:
    from ai_gateway.catalog.scheduler import ModelSyncScheduler

    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    unique_name = f"scheduler-lock-{datetime.now(UTC).timestamp()}"
    async with session_factory() as setup_session:
        provider = _provider(sync_settings, name=unique_name)
        provider.last_model_sync_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
        setup_session.add(provider)
        await setup_session.commit()
        provider_id = provider.id

    entered = asyncio.Event()
    release = asyncio.Event()
    sync_calls: list[int] = []

    async def fake_sync(provider_id: int, **_: Any) -> object:
        sync_calls.append(provider_id)
        entered.set()
        await release.wait()
        return object()

    factory = FakeHttpClientFactory(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
    )
    scheduler_a = ModelSyncScheduler(
        engine=test_engine,
        session_factory=session_factory,
        http_client_factory=factory,
        settings=sync_settings,
        sync_provider=fake_sync,
    )
    scheduler_b = ModelSyncScheduler(
        engine=test_engine,
        session_factory=session_factory,
        http_client_factory=factory,
        settings=sync_settings,
        sync_provider=fake_sync,
    )
    first_task = asyncio.create_task(scheduler_a.run_once())
    await asyncio.wait_for(entered.wait(), timeout=2)
    await scheduler_b.run_once()
    release.set()
    await first_task
    await factory.client.aclose()

    try:
        assert sync_calls == [provider_id]
    finally:
        async with session_factory() as cleanup_session:
            await cleanup_session.execute(
                delete(ProviderProtocol).where(ProviderProtocol.provider_id == provider_id)
            )
            await cleanup_session.execute(delete(Provider).where(Provider.id == provider_id))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_scheduler_selects_only_enabled_auto_load_and_due_providers(
    test_engine: AsyncEngine,
    sync_settings: Settings,
) -> None:
    from ai_gateway.catalog.scheduler import ModelSyncScheduler

    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    prefix = f"scheduler-due-{datetime.now(UTC).timestamp()}"
    now = datetime.now(UTC).replace(tzinfo=None)
    providers = [
        _provider(sync_settings, name=f"{prefix}-due"),
        _provider(sync_settings, name=f"{prefix}-disabled", enabled=False),
        _provider(sync_settings, name=f"{prefix}-manual", auto_load_models=False),
        _provider(sync_settings, name=f"{prefix}-recent"),
    ]
    providers[-1].last_model_sync_at = now
    async with session_factory() as setup_session:
        setup_session.add_all(providers)
        await setup_session.commit()
        provider_ids = [provider.id for provider in providers]

    sync_calls: list[int] = []

    async def fake_sync(provider_id: int, **_: Any) -> object:
        sync_calls.append(provider_id)
        return object()

    factory = FakeHttpClientFactory(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
    )
    scheduler = ModelSyncScheduler(
        engine=test_engine,
        session_factory=session_factory,
        http_client_factory=factory,
        settings=sync_settings,
        sync_provider=fake_sync,
        clock=lambda: now,
    )
    await scheduler.run_once()
    await factory.client.aclose()

    try:
        assert sync_calls == [providers[0].id]
    finally:
        async with session_factory() as cleanup_session:
            await cleanup_session.execute(
                delete(ProviderProtocol).where(ProviderProtocol.provider_id.in_(provider_ids))
            )
            await cleanup_session.execute(delete(Provider).where(Provider.id.in_(provider_ids)))
            await cleanup_session.commit()
