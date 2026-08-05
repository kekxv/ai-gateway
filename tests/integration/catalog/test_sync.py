from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import orjson
import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload

from ai_gateway.admin.model_sync import discover_provider_models, sync_provider_models
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
@pytest.mark.parametrize("operation", ["discover", "sync"])
async def test_model_discovery_releases_orm_connection_during_upstream_io(
    test_engine: AsyncEngine,
    sync_settings: Settings,
    operation: str,
) -> None:
    database_url = test_engine.url.render_as_string(hide_password=False)
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.1,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    provider_name = f"pool-discovery-{operation}-{uuid4().hex}"
    async with sessions() as setup_session:
        provider = _provider(sync_settings, name=provider_name)
        setup_session.add(provider)
        await setup_session.commit()
        provider_id = provider.id

    def handler(request: httpx.Request) -> httpx.Response:
        checked_out = engine.sync_engine.pool.checkedout()  # type: ignore[attr-defined]
        assert checked_out == 0, "ORM connection was retained across upstream discovery I/O"
        return _json_response(request, {"data": [], "has_more": False})

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        async with sessions() as discovery_session:
            if operation == "discover":
                await discover_provider_models(
                    provider_id,
                    session=discovery_session,
                    http_client_factory=FakeHttpClientFactory(upstream_client),
                    settings=sync_settings,
                    release_connection_before_discovery=True,
                )
            else:
                await sync_provider_models(
                    provider_id,
                    session=discovery_session,
                    http_client_factory=FakeHttpClientFactory(upstream_client),
                    settings=sync_settings,
                    release_connection_before_discovery=True,
                )
    finally:
        await upstream_client.aclose()
        async with sessions() as cleanup_session:
            await cleanup_session.execute(
                delete(ModelRoute).where(ModelRoute.provider_id == provider_id)
            )
            await cleanup_session.execute(
                delete(ProviderProtocol).where(ProviderProtocol.provider_id == provider_id)
            )
            await cleanup_session.execute(delete(Provider).where(Provider.id == provider_id))
            await cleanup_session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_scheduler_retains_only_advisory_lock_connection_during_discovery(
    test_engine: AsyncEngine,
    sync_settings: Settings,
) -> None:
    from ai_gateway.catalog.scheduler import ModelSyncScheduler

    database_url = test_engine.url.render_as_string(hide_password=False)
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.1,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    provider_name = f"scheduler-pool-discovery-{uuid4().hex}"
    async with sessions() as setup_session:
        provider = _provider(sync_settings, name=provider_name)
        setup_session.add(provider)
        await setup_session.commit()
        provider_id = provider.id

    def handler(request: httpx.Request) -> httpx.Response:
        checked_out = engine.sync_engine.pool.checkedout()  # type: ignore[attr-defined]
        assert checked_out == 1, "scheduler retained an ORM connection in addition to GET_LOCK"
        return _json_response(request, {"data": [], "has_more": False})

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    scheduler = ModelSyncScheduler(
        engine=engine,
        session_factory=sessions,
        http_client_factory=FakeHttpClientFactory(upstream_client),
        settings=sync_settings,
    )
    try:
        await scheduler.run_once()
    finally:
        await upstream_client.aclose()
        async with sessions() as cleanup_session:
            await cleanup_session.execute(
                delete(ModelRoute).where(ModelRoute.provider_id == provider_id)
            )
            await cleanup_session.execute(
                delete(ProviderProtocol).where(ProviderProtocol.provider_id == provider_id)
            )
            await cleanup_session.execute(delete(Provider).where(Provider.id == provider_id))
            await cleanup_session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_sync_does_not_resolve_discovered_model_ids_through_aliases(
    session: AsyncSession,
    sync_settings: Settings,
) -> None:
    provider = _provider(sync_settings, name="sync-idempotent")
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
                upstream_model="stale-upstream-name",
                enabled=False,
                source=RouteSource.DISCOVERED,
            ),
            ModelRoute(
                model=missing_model,
                upstream_model="native-missing",
                enabled=True,
                source=RouteSource.DISCOVERED,
            ),
            ModelRoute(
                model=manual_model,
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
    assert model_names.count("alias-native") == 1
    assert model_names.count("native-new") == 1
    assert [alias.alias for alias in alias_model.aliases] == ["alias-native"]
    assert "alias-target" not in routes_by_model
    assert routes_by_model["alias-native"].upstream_model == "alias-native"
    assert routes_by_model["alias-native"].source is RouteSource.DISCOVERED
    assert routes_by_model["native-found"].upstream_model == "native-found"
    assert routes_by_model["native-found"].enabled is True
    assert routes_by_model["native-missing"].enabled is False
    assert routes_by_model["manual-model"].upstream_model == "manual-upstream"
    assert routes_by_model["manual-model"].enabled is True
    assert routes_by_model["manual-model"].source is RouteSource.MANUAL
    assert provider.last_model_sync_at is not None
    assert len(factory.urls) == 2


@pytest.mark.asyncio
async def test_sync_prefers_openai_discovery_when_multiple_protocols_are_enabled(
    session: AsyncSession,
    sync_settings: Settings,
) -> None:
    provider = _provider(
        sync_settings,
        name="sync-openai-preferred",
        protocols=(Protocol.OPENAI, Protocol.CLAUDE),
    )
    session.add(provider)
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://openai.example/v1/models"
        return _json_response(
            request,
            {"data": [{"id": "openai-discovered"}], "has_more": False},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        factory = FakeHttpClientFactory(client)
        result = await sync_provider_models(
            provider.id,
            session=session,
            http_client_factory=factory,
            settings=sync_settings,
        )

    routes = list(
        await session.scalars(select(ModelRoute).where(ModelRoute.provider_id == provider.id))
    )
    assert result.discovered_models == 1
    assert factory.urls == ["https://openai.example/v1/models"]
    assert len(routes) == 1
    assert routes[0].upstream_model == "openai-discovered"


@pytest.mark.asyncio
async def test_discovery_endpoint_logic_prefers_openai_when_multiple_protocols_are_enabled(
    session: AsyncSession,
    sync_settings: Settings,
) -> None:
    provider = _provider(
        sync_settings,
        name="discover-openai-preferred",
        protocols=(Protocol.OPENAI, Protocol.CLAUDE),
    )
    session.add(provider)
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://openai.example/v1/models"
        return _json_response(
            request,
            {"data": [{"id": "openai-discovered"}], "has_more": False},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        factory = FakeHttpClientFactory(client)
        result = await discover_provider_models(
            provider.id,
            session=session,
            http_client_factory=factory,
            settings=sync_settings,
        )

    assert result == {"openai": ["openai-discovered"]}
    assert factory.urls == ["https://openai.example/v1/models"]


@pytest.mark.asyncio
async def test_failed_discovery_does_not_apply_catalog_changes(
    session: AsyncSession,
    sync_settings: Settings,
) -> None:
    provider = _provider(sync_settings, name="sync-atomic-failure")
    stale_model = Model(canonical_name="stale-discovered", display_name="Stale")
    provider.routes.append(
        ModelRoute(
            model=stale_model,
            upstream_model="stale-discovered",
            source=RouteSource.DISCOVERED,
            enabled=True,
        )
    )
    session.add(provider)
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "temporary"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await sync_provider_models(
                provider.id,
                session=session,
                http_client_factory=FakeHttpClientFactory(client),
                settings=sync_settings,
            )

    assert provider.routes[0].enabled is True
    assert provider.last_model_sync_at is None


@pytest.mark.asyncio
async def test_concurrent_providers_share_one_new_canonical_model(
    test_engine: AsyncEngine,
    sync_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_gateway.admin import model_sync as model_sync_module

    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    suffix = str(datetime.now(UTC).timestamp()).replace(".", "-")
    canonical_name = f"shared-concurrent-model-{suffix}"
    providers = [
        _provider(sync_settings, name=f"concurrent-provider-a-{suffix}"),
        _provider(sync_settings, name=f"concurrent-provider-b-{suffix}"),
    ]
    async with session_factory() as setup_session:
        setup_session.add_all(providers)
        await setup_session.commit()
        provider_ids = [provider.id for provider in providers]

    original_lookup = model_sync_module._models_by_discovered_name
    lookup_count = 0
    lookup_lock = asyncio.Lock()
    both_looked_up = asyncio.Event()

    async def synchronized_lookup(
        session: AsyncSession,
        names: set[str],
    ) -> dict[str, Model]:
        nonlocal lookup_count
        result = await original_lookup(session, names)
        async with lookup_lock:
            lookup_count += 1
            if lookup_count == 2:
                both_looked_up.set()
        await asyncio.wait_for(both_looked_up.wait(), timeout=2)
        return result

    monkeypatch.setattr(model_sync_module, "_models_by_discovered_name", synchronized_lookup)

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            request,
            {"data": [{"id": canonical_name}], "has_more": False},
        )

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            factory = FakeHttpClientFactory(client)
            async with session_factory() as first_session, session_factory() as second_session:
                results = await asyncio.gather(
                    sync_provider_models(
                        provider_ids[0],
                        session=first_session,
                        http_client_factory=factory,
                        settings=sync_settings,
                    ),
                    sync_provider_models(
                        provider_ids[1],
                        session=second_session,
                        http_client_factory=factory,
                        settings=sync_settings,
                    ),
                )

        async with session_factory() as verification_session:
            models = list(
                await verification_session.scalars(
                    select(Model).where(Model.canonical_name == canonical_name)
                )
            )
            routes = list(
                await verification_session.scalars(
                    select(ModelRoute).where(ModelRoute.provider_id.in_(provider_ids))
                )
            )

        assert [result.provider_id for result in results] == provider_ids
        assert len(models) == 1
        assert {route.provider_id for route in routes} == set(provider_ids)
        assert {route.model_id for route in routes} == {models[0].id}
        assert all(route.source is RouteSource.DISCOVERED for route in routes)
    finally:
        async with session_factory() as cleanup_session:
            await cleanup_session.execute(
                delete(ModelRoute).where(ModelRoute.provider_id.in_(provider_ids))
            )
            await cleanup_session.execute(
                delete(ProviderProtocol).where(ProviderProtocol.provider_id.in_(provider_ids))
            )
            await cleanup_session.execute(delete(Provider).where(Provider.id.in_(provider_ids)))
            await cleanup_session.execute(
                delete(Model).where(Model.canonical_name == canonical_name)
            )
            await cleanup_session.commit()


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
@pytest.mark.parametrize(
    ("method", "endpoint"),
    [("GET", "discover-models"), ("POST", "sync-models")],
)
async def test_model_sync_endpoints_log_upstream_failure_at_warning_level(
    session: AsyncSession,
    sync_settings: Settings,
    caplog: pytest.LogCaptureFixture,
    method: str,
    endpoint: str,
) -> None:
    provider = _provider(sync_settings, name="discovery-warning")
    admin = User(
        email="discovery-warning-admin@example.com",
        password_hash=hash_password("discovery-warning-admin-password"),
        role="admin",
        account=Account(),
    )
    session.add_all([provider, admin])
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "temporary"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream_client:
        app = create_app(sync_settings)
        app.state.http_client_factory = FakeHttpClientFactory(upstream_client)

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_settings] = lambda: sync_settings
        token = issue_access_token(user_id=admin.id, settings=sync_settings)
        caplog.set_level(logging.WARNING, logger="uvicorn")
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"authorization": f"Bearer {token}"},
        ) as client:
            response = await client.request(
                method,
                f"/admin/providers/{provider.id}/{endpoint}",
            )

    records = [record for record in caplog.records if record.name == "uvicorn"]
    assert response.status_code == 502
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert f"provider_id={provider.id}" in records[0].getMessage()
    assert "HTTPStatusError" in records[0].getMessage()
    assert "503 Service Unavailable" in records[0].getMessage()
    assert "https://openai.example/v1/models" in records[0].getMessage()


@pytest.mark.asyncio
async def test_discovery_endpoint_returns_sanitized_upstream_error_detail(
    session: AsyncSession,
    sync_settings: Settings,
) -> None:
    provider = _provider(sync_settings, name="discovery-error-detail")
    admin = User(
        email="discovery-error-detail-admin@example.com",
        password_hash=hash_password("discovery-error-detail-admin-password"),
        role="admin",
        account=Account(),
    )
    session.add_all([provider, admin])
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "error": {
                    "message": "Incorrect API key",
                    "type": "authentication_error",
                    "api_key": "sk-upstream-secret-value",
                }
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream_client:
        app = create_app(sync_settings)
        app.state.http_client_factory = FakeHttpClientFactory(upstream_client)

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
            response = await client.get(f"/admin/providers/{provider.id}/discover-models")

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "model_discovery_failed",
            "message": (
                "Upstream provider returned 401 Unauthorized: "
                '{"error":{"message":"Incorrect API key","type":"authentication_error",'
                '"api_key":"[REDACTED]"}}'
            ),
        }
    }
    assert "sk-upstream-secret-value" not in response.text


@pytest.mark.asyncio
async def test_custom_app_scopes_endpoint_and_scheduler_dependencies(
    test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_gateway import main as main_module
    from ai_gateway.db import session as db_session_module

    database_url = test_engine.url.render_as_string(hide_password=False)
    custom_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        jwt_secret="custom-app-jwt-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    suffix = str(datetime.now(UTC).timestamp()).replace(".", "-")
    async with session_factory() as setup_session:
        provider = _provider(custom_settings, name=f"custom-app-provider-{suffix}")
        admin = User(
            email=f"custom-app-admin-{suffix}@example.com",
            password_hash=hash_password("custom-app-password"),
            role="admin",
            account=Account(),
        )
        setup_session.add_all([provider, admin])
        await setup_session.commit()
        provider_id = provider.id
        admin_id = admin.id

    factory_instances: list[AppHttpClientFactory] = []
    scheduler_instances: list[CapturingScheduler] = []

    class AppHttpClientFactory:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings
            self.urls: list[str] = []
            self.client = httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: _json_response(
                        request,
                        {"data": [{"id": f"custom-app-model-{suffix}"}], "has_more": False},
                    )
                )
            )
            factory_instances.append(self)

        async def client_for(self, url: str | httpx.URL) -> httpx.AsyncClient:
            self.urls.append(str(url))
            return self.client

        async def aclose(self) -> None:
            await self.client.aclose()

    class CapturingScheduler:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.stopped = asyncio.Event()
            scheduler_instances.append(self)

        async def run(self) -> None:
            await self.stopped.wait()

        def stop(self) -> None:
            self.stopped.set()

    def forbidden_global_session_factory() -> object:
        pytest.fail("custom app endpoint must not use the global session factory")

    monkeypatch.setattr(main_module, "HttpClientFactory", AppHttpClientFactory)
    monkeypatch.setattr(main_module, "ModelSyncScheduler", CapturingScheduler)
    monkeypatch.setattr(
        db_session_module,
        "get_session_factory",
        forbidden_global_session_factory,
    )
    app = create_app(custom_settings)
    token = issue_access_token(user_id=admin_id, settings=custom_settings)

    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"authorization": f"Bearer {token}"},
            ) as client:
                response = await client.post(f"/admin/providers/{provider_id}/sync-models")

            assert response.status_code == 200, response.text
            assert response.json()["discovered_models"] == 1
            assert app.state.settings is custom_settings
            assert app.state.session_factory is not session_factory
            assert factory_instances[0].settings is custom_settings
            assert scheduler_instances[0].kwargs["settings"] is custom_settings
            assert scheduler_instances[0].kwargs["session_factory"] is app.state.session_factory
            assert scheduler_instances[0].kwargs["http_client_factory"] is factory_instances[0]
    finally:
        async with session_factory() as cleanup_session:
            await cleanup_session.execute(
                delete(ModelRoute).where(ModelRoute.provider_id == provider_id)
            )
            await cleanup_session.execute(
                delete(Model).where(Model.canonical_name == f"custom-app-model-{suffix}")
            )
            await cleanup_session.execute(
                delete(ProviderProtocol).where(ProviderProtocol.provider_id == provider_id)
            )
            await cleanup_session.execute(delete(Provider).where(Provider.id == provider_id))
            await cleanup_session.execute(delete(Account).where(Account.user_id == admin_id))
            await cleanup_session.execute(delete(User).where(User.id == admin_id))
            await cleanup_session.commit()


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
