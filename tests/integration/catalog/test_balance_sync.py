"""Integration tests for provider upstream balance queries."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
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

from ai_gateway.catalog.balance_scheduler import BalanceSyncScheduler
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import BalanceQueryType, Protocol
from ai_gateway.core.security import encrypt_secret, hash_password, issue_access_token
from ai_gateway.db.models import Account, Provider, ProviderProtocol, User
from ai_gateway.db.session import get_session
from ai_gateway.main import create_app


class FakeHttpClientFactory:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.urls: list[str] = []

    async def client_for(
        self,
        url: str | httpx.URL,
        *,
        provider_id: int | None = None,
        proxy_config_encrypted: bytes | None = None,
    ) -> httpx.AsyncClient:
        self.urls.append(str(url))
        return self.client


@pytest.fixture
def balance_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret="balance-integration-jwt-secret-at-least-32",
        encryption_key=Fernet.generate_key().decode(),
    )


def _encrypted_json(value: dict[str, object], settings: Settings) -> bytes:
    return encrypt_secret(orjson.dumps(value).decode(), settings=settings)


def _provider(
    settings: Settings,
    *,
    name: str,
    base_url: str = "https://newapi.example/v1",
    query_type: BalanceQueryType | None = None,
    balance_config: dict[str, object] | None = None,
    auto_sync: bool = False,
    interval_seconds: int = 60,
) -> Provider:
    return Provider(
        name=name,
        credential_encrypted=_encrypted_json({"api_key": "sk-provider"}, settings),
        enabled=True,
        auto_load_models=False,
        model_sync_interval_seconds=60,
        balance_query_type=query_type,
        balance_query_config_encrypted=(
            _encrypted_json(balance_config, settings) if balance_config else None
        ),
        balance_auto_sync=auto_sync,
        balance_sync_interval_seconds=interval_seconds,
        protocols=[
            ProviderProtocol(protocol=Protocol.OPENAI, base_url=base_url, enabled=True),
        ],
    )


def _admin(settings: Settings) -> User:
    return User(
        email=f"balance-admin-{uuid4().hex}@example.com",
        password_hash=hash_password("balance-admin-password"),
        role="admin",
        account=Account(),
    )


@asynccontextmanager
async def _api(
    session: AsyncSession,
    settings: Settings,
    admin: User,
    handler: Any,
) -> AsyncIterator[tuple[AsyncClient, FakeHttpClientFactory]]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream_client:
        factory = FakeHttpClientFactory(upstream_client)
        app = create_app(settings)
        app.state.http_client_factory = factory

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_settings] = lambda: settings
        token = issue_access_token(user_id=admin.id, settings=settings)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"authorization": f"Bearer {token}"},
        ) as client:
            yield client, factory


def _new_api_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"success": True, "data": {"quota": 1250000, "used_quota": 250000}},
        request=request,
    )


@pytest.mark.asyncio
async def test_provider_api_round_trips_balance_configuration(
    session: AsyncSession,
    balance_settings: Settings,
) -> None:
    admin = _admin(balance_settings)
    session.add(admin)
    await session.flush()

    async with _api(session, balance_settings, admin, _new_api_handler) as (client, factory):
        created = await client.post(
            "/admin/providers",
            json={
                "name": f"balance-crud-{uuid4().hex}",
                "credential": {"api_key": "sk-provider"},
                "protocols": [{"protocol": "openai", "base_url": "https://newapi.example/v1"}],
                "balance_query_type": "new_api",
                "balance_config": {"user_id": "12", "api_key": "access-token"},
                "balance_auto_sync": True,
                "balance_sync_interval_seconds": 900,
            },
        )
        assert created.status_code == 201, created.text
        provider_id = created.json()["id"]
        balance = created.json()["balance"]
        assert balance["query_type"] == "new_api"
        assert balance["auto_sync"] is True
        assert balance["sync_interval_seconds"] == 900
        assert balance["config"]["has_api_key"] is True
        assert balance["config"]["user_id"] == "12"
        assert balance["amount"] is None

        synced = await client.post(f"/admin/providers/{provider_id}/balance/sync")
        assert synced.status_code == 200, synced.text
        assert synced.json()["amount"] == "2.50000000"
        assert synced.json()["used"] == "0.50000000"
        assert synced.json()["currency"] == "USD"
        assert factory.urls == ["https://newapi.example/v1"]

        fetched = await client.get(f"/admin/providers/{provider_id}")
        assert fetched.json()["balance"]["amount"] == "2.50000000"
        assert fetched.json()["balance"]["error"] is None

        # Omitting the secret keeps the stored override.
        updated = await client.patch(
            f"/admin/providers/{provider_id}",
            json={"balance_config": {"user_id": "34"}},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["balance"]["config"]["user_id"] == "34"
        assert updated.json()["balance"]["config"]["has_api_key"] is True
        assert updated.json()["balance"]["amount"] == "2.50000000"

        # Clearing the secret is explicit.
        cleared = await client.patch(
            f"/admin/providers/{provider_id}",
            json={"balance_config": {"api_key": None}},
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["balance"]["config"]["has_api_key"] is False

        # Disabling the feature drops the stored snapshot.
        disabled = await client.patch(
            f"/admin/providers/{provider_id}",
            json={"balance_query_type": None},
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["balance"]["query_type"] is None
        assert disabled.json()["balance"]["amount"] is None


@pytest.mark.asyncio
async def test_provider_create_accepts_explicitly_empty_balance_fields(
    session: AsyncSession,
    balance_settings: Settings,
) -> None:
    """The console always submits non-secret fields, as null when they are empty."""

    admin = _admin(balance_settings)
    session.add(admin)
    await session.flush()

    async with _api(session, balance_settings, admin, _new_api_handler) as (client, _):
        created = await client.post(
            "/admin/providers",
            json={
                "name": f"balance-nulls-{uuid4().hex}",
                "credential": {"api_key": "sk-provider"},
                "protocols": [{"protocol": "openai", "base_url": "https://newapi.example/v1"}],
                "balance_query_type": "custom",
                "balance_config": {
                    "base_url": None,
                    "user_id": None,
                    "currency": None,
                    "divisor": None,
                    "path": "/api/balance",
                    "method": "GET",
                    "amount_path": "data.quota",
                    "used_path": None,
                    "available_path": None,
                },
            },
        )

    assert created.status_code == 201, created.text
    config = created.json()["balance"]["config"]
    assert config["base_url"] is None
    assert config["user_id"] is None
    assert config["currency"] is None
    assert config["divisor"] is None
    assert config["path"] == "/api/balance"
    assert config["amount_path"] == "data.quota"


@pytest.mark.asyncio
async def test_clearing_balance_overrides_restores_defaults(
    session: AsyncSession,
    balance_settings: Settings,
) -> None:
    admin = _admin(balance_settings)
    provider = _provider(
        balance_settings,
        name=f"balance-clear-{uuid4().hex}",
        query_type=BalanceQueryType.NEW_API,
        balance_config={
            "base_url": "https://override.example",
            "user_id": "12",
            "currency": "CNY",
            "divisor": "1",
        },
    )
    session.add_all([admin, provider])
    await session.flush()

    async with _api(session, balance_settings, admin, _new_api_handler) as (client, factory):
        before = await client.post(f"/admin/providers/{provider.id}/balance/sync")
        assert before.status_code == 200, before.text
        assert before.json()["amount"] == "1250000.00000000"
        assert before.json()["currency"] == "CNY"
        assert factory.urls == ["https://override.example"]

        cleared = await client.patch(
            f"/admin/providers/{provider.id}",
            json={
                "balance_config": {
                    "base_url": None,
                    "user_id": None,
                    "currency": None,
                    "divisor": None,
                }
            },
        )
        assert cleared.status_code == 200, cleared.text
        config = cleared.json()["balance"]["config"]
        assert config["base_url"] is None
        assert config["user_id"] is None
        assert config["currency"] is None
        assert config["divisor"] is None

        after = await client.post(f"/admin/providers/{provider.id}/balance/sync")

    assert after.status_code == 200, after.text
    assert after.json()["amount"] == "2.50000000"
    assert after.json()["currency"] == "USD"
    assert factory.urls == ["https://override.example", "https://newapi.example/v1"]


@pytest.mark.asyncio
async def test_switching_balance_type_drops_the_stale_snapshot(
    session: AsyncSession,
    balance_settings: Settings,
) -> None:
    admin = _admin(balance_settings)
    provider = _provider(
        balance_settings,
        name=f"balance-switch-{uuid4().hex}",
        query_type=BalanceQueryType.NEW_API,
    )
    session.add_all([admin, provider])
    await session.flush()

    async with _api(session, balance_settings, admin, _new_api_handler) as (client, _):
        synced = await client.post(f"/admin/providers/{provider.id}/balance/sync")
        assert synced.status_code == 200, synced.text

        switched = await client.patch(
            f"/admin/providers/{provider.id}",
            json={"balance_query_type": "openrouter"},
        )

    assert switched.status_code == 200, switched.text
    assert switched.json()["balance"]["query_type"] == "openrouter"
    assert switched.json()["balance"]["amount"] is None
    assert switched.json()["balance"]["updated_at"] is None


@pytest.mark.asyncio
async def test_provider_api_rejects_incomplete_custom_balance_configuration(
    session: AsyncSession,
    balance_settings: Settings,
) -> None:
    admin = _admin(balance_settings)
    session.add(admin)
    await session.flush()

    async with _api(session, balance_settings, admin, _new_api_handler) as (client, _):
        response = await client.post(
            "/admin/providers",
            json={
                "name": f"balance-invalid-{uuid4().hex}",
                "credential": {"api_key": "sk-provider"},
                "balance_query_type": "custom",
                "balance_config": {"path": "/balance"},
            },
        )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "invalid_balance_config"


@pytest.mark.asyncio
async def test_balance_sync_requires_a_configured_type(
    session: AsyncSession,
    balance_settings: Settings,
) -> None:
    admin = _admin(balance_settings)
    provider = _provider(balance_settings, name=f"balance-unconfigured-{uuid4().hex}")
    session.add_all([admin, provider])
    await session.flush()

    async with _api(session, balance_settings, admin, _new_api_handler) as (client, _):
        response = await client.post(f"/admin/providers/{provider.id}/balance/sync")

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "balance_query_not_configured"


@pytest.mark.asyncio
async def test_balance_sync_records_upstream_failure(
    session: AsyncSession,
    balance_settings: Settings,
) -> None:
    admin = _admin(balance_settings)
    provider = _provider(
        balance_settings,
        name=f"balance-failure-{uuid4().hex}",
        query_type=BalanceQueryType.NEW_API,
    )
    session.add_all([admin, provider])
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "bad token"}, request=request)

    async with _api(session, balance_settings, admin, handler) as (client, _):
        response = await client.post(f"/admin/providers/{provider.id}/balance/sync")

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "balance_sync_failed"
    assert "access token" in response.json()["detail"]["message"]
    stored = await session.get(Provider, provider.id)
    assert stored is not None
    await session.refresh(stored)
    assert stored.balance_error is not None
    assert "401" in stored.balance_error
    assert "access token" in stored.balance_error
    assert stored.last_balance_sync_at is not None
    assert stored.balance_amount is None


@pytest.mark.asyncio
async def test_balance_detection_applies_an_unambiguous_match(
    session: AsyncSession,
    balance_settings: Settings,
) -> None:
    admin = _admin(balance_settings)
    provider = _provider(
        balance_settings,
        name=f"balance-detect-single-{uuid4().hex}",
        base_url="https://api.deepseek.com/v1",
    )
    session.add_all([admin, provider])
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/balance":
            return httpx.Response(
                200,
                json={
                    "is_available": True,
                    "balance_infos": [{"currency": "USD", "total_balance": "4.20"}],
                },
                request=request,
            )
        return httpx.Response(404, json={"error": "not found"}, request=request)

    async with _api(session, balance_settings, admin, handler) as (client, _):
        response = await client.post(f"/admin/providers/{provider.id}/balance/detect")

    assert response.status_code == 200, response.text
    assert response.json()["applied"] == "deepseek"
    assert [item["query_type"] for item in response.json()["candidates"]] == ["deepseek"]
    stored = await session.get(Provider, provider.id)
    assert stored is not None
    await session.refresh(stored)
    assert stored.balance_query_type is BalanceQueryType.DEEPSEEK
    assert str(stored.balance_amount) == "4.20000000"
    assert stored.balance_updated_at is not None


@pytest.mark.asyncio
async def test_balance_detection_defers_ambiguous_matches(
    session: AsyncSession,
    balance_settings: Settings,
) -> None:
    admin = _admin(balance_settings)
    provider = _provider(balance_settings, name=f"balance-detect-multi-{uuid4().hex}")
    session.add_all([admin, provider])
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/user/self":
            return httpx.Response(200, json={"data": {"quota": 500000}}, request=request)
        if request.url.path == "/user/balance":
            return httpx.Response(
                200,
                json={"balance_infos": [{"currency": "USD", "total_balance": "1"}]},
                request=request,
            )
        return httpx.Response(404, json={"error": "not found"}, request=request)

    async with _api(session, balance_settings, admin, handler) as (client, _):
        response = await client.post(f"/admin/providers/{provider.id}/balance/detect")

    assert response.status_code == 200, response.text
    assert response.json()["applied"] is None
    assert {item["query_type"] for item in response.json()["candidates"]} == {
        "new_api",
        "deepseek",
    }
    stored = await session.get(Provider, provider.id)
    assert stored is not None
    await session.refresh(stored)
    assert stored.balance_query_type is None


@pytest.mark.asyncio
async def test_balance_detection_reports_when_no_upstream_responds(
    session: AsyncSession,
    balance_settings: Settings,
) -> None:
    admin = _admin(balance_settings)
    provider = _provider(balance_settings, name=f"balance-detect-none-{uuid4().hex}")
    session.add_all([admin, provider])
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/user/self":
            return httpx.Response(
                401,
                json={
                    "code": "AUTH_UNAUTHORIZED",
                    "message": "Unauthorized, invalid access token",
                    "success": False,
                },
                request=request,
            )
        return httpx.Response(404, json={"error": "not found"}, request=request)

    async with _api(session, balance_settings, admin, handler) as (client, _):
        response = await client.post(f"/admin/providers/{provider.id}/balance/detect")

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "balance_detection_failed"
    message = response.json()["detail"]["message"]
    assert "new_api: Upstream provider returned 401" in message
    assert "invalid access token" in message
    assert "deepseek: Upstream provider returned 404" in message
    assert "access token" in message


@pytest.mark.asyncio
async def test_balance_scheduler_syncs_only_due_providers(
    test_engine: AsyncEngine,
    balance_settings: Settings,
) -> None:
    database_url = test_engine.url.render_as_string(hide_password=False)
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.1,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    names = {
        "due": f"balance-scheduler-due-{suffix}",
        "manual": f"balance-scheduler-manual-{suffix}",
        "recent": f"balance-scheduler-recent-{suffix}",
        "disabled": f"balance-scheduler-disabled-{suffix}",
    }
    now = datetime(2026, 9, 22, 12, 0, 0)
    async with sessions() as setup_session:
        due = _provider(
            balance_settings,
            name=names["due"],
            query_type=BalanceQueryType.NEW_API,
            auto_sync=True,
        )
        manual = _provider(
            balance_settings,
            name=names["manual"],
            query_type=BalanceQueryType.NEW_API,
        )
        recent = _provider(
            balance_settings,
            name=names["recent"],
            query_type=BalanceQueryType.NEW_API,
            auto_sync=True,
        )
        recent.last_balance_sync_at = now - timedelta(seconds=10)
        disabled = _provider(
            balance_settings,
            name=names["disabled"],
            query_type=BalanceQueryType.NEW_API,
            auto_sync=True,
        )
        disabled.enabled = False
        setup_session.add_all([due, manual, recent, disabled])
        await setup_session.commit()
        provider_ids = {
            "due": due.id,
            "manual": manual.id,
            "recent": recent.id,
            "disabled": disabled.id,
        }

    async with httpx.AsyncClient(transport=httpx.MockTransport(_new_api_handler)) as upstream:
        scheduler = BalanceSyncScheduler(
            engine=engine,
            session_factory=sessions,
            http_client_factory=FakeHttpClientFactory(upstream),
            settings=balance_settings,
            clock=lambda: now,
        )
        try:
            await scheduler.run_once()
        finally:
            await upstream.aclose()

    try:
        async with sessions() as verify_session:
            rows = {
                row.name: row
                for row in await verify_session.scalars(
                    select(Provider).where(Provider.name.in_(list(names.values())))
                )
            }
        assert str(rows[names["due"]].balance_amount) == "2.50000000"
        assert rows[names["due"]].balance_error is None
        for key in ("manual", "recent", "disabled"):
            assert rows[names[key]].balance_amount is None
        assert rows[names["manual"]].last_balance_sync_at is None
        assert rows[names["disabled"]].last_balance_sync_at is None
        assert rows[names["recent"]].last_balance_sync_at == now - timedelta(seconds=10)
    finally:
        async with sessions() as cleanup_session:
            await cleanup_session.execute(
                delete(ProviderProtocol).where(
                    ProviderProtocol.provider_id.in_(provider_ids.values())
                )
            )
            await cleanup_session.execute(
                delete(Provider).where(Provider.id.in_(provider_ids.values()))
            )
            await cleanup_session.commit()
        await engine.dispose()
