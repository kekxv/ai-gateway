"""Integration tests for upstream model price synchronization."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import orjson
import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import BalanceQueryType, Protocol, RouteSource
from ai_gateway.core.security import encrypt_secret, hash_password, issue_access_token
from ai_gateway.db.models import (
    Account,
    Model,
    ModelPriceTier,
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
def price_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret="price-integration-jwt-secret-at-least-32",
        encryption_key=Fernet.generate_key().decode(),
    )


def _encrypted_json(value: dict[str, object], settings: Settings) -> bytes:
    return encrypt_secret(orjson.dumps(value).decode(), settings=settings)


def _provider(
    settings: Settings,
    *,
    name: str,
    base_url: str = "https://newapi.example/v1",
    balance_config: dict[str, object] | None = None,
    cost_multiplier: str = "1",
) -> Provider:
    return Provider(
        name=name,
        credential_encrypted=_encrypted_json({"api_key": "sk-provider"}, settings),
        enabled=True,
        cost_multiplier=Decimal(cost_multiplier),
        auto_load_models=False,
        model_sync_interval_seconds=60,
        balance_query_type=(BalanceQueryType.NEW_API if balance_config is not None else None),
        balance_query_config_encrypted=(
            _encrypted_json(balance_config, settings) if balance_config else None
        ),
        protocols=[
            ProviderProtocol(protocol=Protocol.OPENAI, base_url=base_url, enabled=True),
        ],
    )


def _routed_model(
    provider: Provider,
    *,
    name: str,
    upstream_model: str | None = None,
    input_price: str = "0",
    output_price: str = "0",
) -> Model:
    model = Model(
        canonical_name=name,
        display_name=name,
        input_price_per_million=Decimal(input_price),
        output_price_per_million=Decimal(output_price),
    )
    model.routes = [
        ModelRoute(
            provider=provider,
            upstream_model=upstream_model or name,
            source=RouteSource.DISCOVERED,
            enabled=True,
        )
    ]
    return model


def _admin(settings: Settings) -> User:
    return User(
        email=f"price-admin-{uuid4().hex}@example.com",
        password_hash=hash_password("price-admin-password"),
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


def _new_api_pricing_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/user/self":
        return httpx.Response(
            200,
            json={"success": True, "data": {"group": "default"}},
            request=request,
        )
    if request.url.path == "/api/pricing":
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    {
                        "model_name": "gpt-4o",
                        "quota_type": 0,
                        "model_ratio": 1.25,
                        "completion_ratio": 4,
                    },
                    {
                        "model_name": "dall-e-3",
                        "quota_type": 1,
                        "model_price": 0.04,
                    },
                ],
                "group_ratio": {"default": 2.5, "svip": 0.25},
            },
            request=request,
        )
    if request.url.path == "/v1/models":
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "gpt-4o", "object": "model"}]},
            request=request,
        )
    return httpx.Response(404, json={"success": False, "message": "not found"}, request=request)


@pytest.mark.asyncio
async def test_price_sync_fills_empty_prices_and_updates_cost_multiplier(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(
        price_settings,
        name=f"price-sync-{uuid4().hex}",
        balance_config={"user_id": "25", "api_key": "access-token"},
    )
    fillable = _routed_model(provider, name=f"gpt-4o-{uuid4().hex}", upstream_model="gpt-4o")
    configured = _routed_model(
        provider,
        name=f"priced-{uuid4().hex}",
        upstream_model="gpt-4o",
        input_price="1.5",
        output_price="6",
    )
    fixed = _routed_model(provider, name=f"dall-e-3-{uuid4().hex}", upstream_model="dall-e-3")
    session.add_all([admin, provider, fillable, configured, fixed])
    await session.flush()

    async with _api(session, price_settings, admin, _new_api_pricing_handler) as (client, _factory):
        response = await client.post(
            f"/admin/providers/{provider.id}/sync-model-prices",
            json={"group": "svip"},
        )

        assert response.status_code == 200, response.text
        body = response.json()

        assert body["group"] == "svip"
        assert body["group_ratio"] == "0.25"
        assert body["cost_multiplier"] == "0.25"
        assert body["cost_multiplier_updated"] is True
        assert body["upstream_models"] == 2
        assert body["updated"] == 1
        assert body["priced"] == 1
        assert body["fixed_price"] == 1
        assert body["unlisted"] == 0

        rows = {row["model_id"]: row for row in body["rows"]}
        assert rows[fillable.id]["status"] == "updated"
        assert rows[fillable.id]["upstream_input_price_per_million"] == "2.50000000"
        assert rows[fillable.id]["upstream_output_price_per_million"] == "10.00000000"
        assert Decimal(rows[fillable.id]["current_input_price_per_million"]) == 0
        # A model that already carries a price is reported, never overwritten.
        assert rows[configured.id]["status"] == "priced"
        assert rows[configured.id]["upstream_input_price_per_million"] == "2.50000000"
        assert rows[configured.id]["current_input_price_per_million"] == "1.50000000"
        assert rows[fixed.id]["status"] == "fixed_price"
        assert Decimal(rows[fixed.id]["upstream_fixed_price"]) == Decimal("0.04")

        fetched = await client.get(f"/admin/providers/{provider.id}")
        assert fetched.json()["cost_multiplier"] == "0.25"
        assert fetched.json()["public_multiplier"] == "1.00"

        model = await client.get(f"/admin/models/{fillable.id}")
        assert model.json()["input_price_per_million"] == "2.50000000"
        assert model.json()["output_price_per_million"] == "10.00000000"

        stored = await client.get(f"/admin/models/{configured.id}")
        assert Decimal(stored.json()["input_price_per_million"]) == Decimal("1.5")
        assert Decimal(stored.json()["output_price_per_million"]) == Decimal("6")


@pytest.mark.asyncio
async def test_price_sync_skips_models_with_price_tiers(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(price_settings, name=f"price-tiers-{uuid4().hex}")
    tiered = _routed_model(provider, name=f"tiered-{uuid4().hex}", upstream_model="gpt-4o")
    tiered.price_tiers = [
        ModelPriceTier(
            max_input_tokens=None,
            input_price_per_million=Decimal("3"),
            output_price_per_million=Decimal("9"),
            cache_read_price_per_million=Decimal("0"),
            cache_write_price_per_million=Decimal("0"),
        )
    ]
    session.add_all([admin, provider, tiered])
    await session.flush()

    async with _api(session, price_settings, admin, _new_api_pricing_handler) as (client, _):
        response = await client.post(f"/admin/providers/{provider.id}/sync-model-prices")

    assert response.status_code == 200, response.text
    rows = {row["model_id"]: row for row in response.json()["rows"]}
    assert rows[tiered.id]["status"] == "priced"
    assert response.json()["updated"] == 0


@pytest.mark.asyncio
async def test_price_sync_reports_models_missing_from_the_upstream_list(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(price_settings, name=f"price-unlisted-{uuid4().hex}")
    unknown = _routed_model(provider, name=f"private-{uuid4().hex}", upstream_model="private-model")
    session.add_all([admin, provider, unknown])
    await session.flush()

    async with _api(session, price_settings, admin, _new_api_pricing_handler) as (client, _):
        response = await client.post(
            f"/admin/providers/{provider.id}/sync-model-prices",
            json={"group": "svip"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unlisted"] == 1
    assert body["rows"][0]["status"] == "unlisted"
    # The selected group ratio is applied even when no price is filled.
    assert body["group"] == "svip"
    assert body["cost_multiplier"] == "0.25"
    assert body["cost_multiplier_updated"] is True


@pytest.mark.asyncio
async def test_price_sync_reports_providers_without_a_pricing_endpoint(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(
        price_settings,
        name=f"price-unsupported-{uuid4().hex}",
        base_url="https://openai.example/v1",
    )
    session.add_all([admin, provider, _routed_model(provider, name=f"plain-{uuid4().hex}")])
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"}, request=request)

    async with _api(session, price_settings, admin, handler) as (client, _):
        response = await client.post(f"/admin/providers/{provider.id}/sync-model-prices")

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "model_price_sync_failed"
    assert "/api/pricing" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_price_sync_reports_unknown_providers(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    session.add(admin)
    await session.flush()

    async with _api(session, price_settings, admin, _new_api_pricing_handler) as (client, _):
        response = await client.post("/admin/providers/999999/sync-model-prices")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "provider_not_found"


@pytest.mark.asyncio
async def test_model_sync_fills_prices_for_upstreams_that_publish_them(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(price_settings, name=f"price-model-sync-{uuid4().hex}")
    session.add_all([admin, provider])
    await session.flush()

    async with _api(session, price_settings, admin, _new_api_pricing_handler) as (client, _):
        response = await client.post(f"/admin/providers/{provider.id}/sync-models")

        assert response.status_code == 200, response.text
        assert response.json()["created_models"] == 1
        assert response.json()["prices_filled"] == 1

        models = await client.get("/admin/models")
        created = next(item for item in models.json() if item["canonical_name"] == "gpt-4o")
        assert created["input_price_per_million"] == "2.50000000"
        assert created["output_price_per_million"] == "10.00000000"


@pytest.mark.asyncio
async def test_model_sync_tolerates_upstreams_without_a_pricing_endpoint(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(
        price_settings,
        name=f"price-model-sync-plain-{uuid4().hex}",
        base_url="https://openai.example/v1",
    )
    session.add_all([admin, provider])
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={"object": "list", "data": [{"id": "plain-model", "object": "model"}]},
                request=request,
            )
        return httpx.Response(404, json={"error": "not found"}, request=request)

    async with _api(session, price_settings, admin, handler) as (client, _):
        response = await client.post(f"/admin/providers/{provider.id}/sync-models")

    assert response.status_code == 200, response.text
    assert response.json()["created_models"] == 1
    assert response.json()["prices_filled"] == 0


@pytest.mark.asyncio
async def test_price_sync_writes_only_the_selected_group(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(
        price_settings,
        name=f"price-select-{uuid4().hex}",
        cost_multiplier="0.80",
    )
    session.add_all(
        [
            admin,
            provider,
            _routed_model(provider, name=f"gpt-4o-{uuid4().hex}", upstream_model="gpt-4o"),
        ]
    )
    await session.flush()

    async with _api(session, price_settings, admin, _new_api_pricing_handler) as (client, _):
        response = await client.post(
            f"/admin/providers/{provider.id}/sync-model-prices",
            json={"group": "svip"},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        # The account group reported by /api/user/self is "default" (2.5x); the relay key sits in
        # svip, so only the explicitly selected group may reach the cost multiplier.
        assert body["group"] == "svip"
        assert body["group_ratio"] == "0.25"
        assert body["cost_multiplier"] == "0.25"
        assert body["cost_multiplier_updated"] is True
        assert body["updated"] == 1

        fetched = await client.get(f"/admin/providers/{provider.id}")
        assert fetched.json()["cost_multiplier"] == "0.25"


@pytest.mark.asyncio
async def test_price_sync_without_a_selected_group_keeps_the_cost_multiplier(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(
        price_settings,
        name=f"price-no-group-{uuid4().hex}",
        cost_multiplier="0.80",
    )
    fillable = _routed_model(provider, name=f"gpt-4o-{uuid4().hex}", upstream_model="gpt-4o")
    session.add_all([admin, provider, fillable])
    await session.flush()
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return _new_api_pricing_handler(request)

    async with _api(session, price_settings, admin, handler) as (client, _):
        response = await client.post(f"/admin/providers/{provider.id}/sync-model-prices")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["group"] is None
        assert body["group_ratio"] is None
        assert body["cost_multiplier"] == "0.80"
        assert body["cost_multiplier_updated"] is False
        # Prices are group independent, so they are still filled.
        assert body["updated"] == 1

        fetched = await client.get(f"/admin/providers/{provider.id}")
        assert fetched.json()["cost_multiplier"] == "0.80"

        model = await client.get(f"/admin/models/{fillable.id}")
        assert model.json()["input_price_per_million"] == "2.50000000"

    assert paths == ["/api/pricing"]


@pytest.mark.asyncio
async def test_price_sync_without_a_selected_group_does_not_warn(
    session: AsyncSession,
    price_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(price_settings, name=f"price-quiet-{uuid4().hex}")
    session.add_all(
        [
            admin,
            provider,
            _routed_model(provider, name=f"gpt-4o-{uuid4().hex}", upstream_model="gpt-4o"),
        ]
    )
    await session.flush()

    with caplog.at_level(logging.WARNING, logger="uvicorn"):
        async with _api(session, price_settings, admin, _new_api_pricing_handler) as (client, _):
            response = await client.post(f"/admin/providers/{provider.id}/sync-model-prices")

    assert response.status_code == 200, response.text
    # Leaving the cost multiplier alone is a normal outcome, not a rejected ratio.
    assert "out-of-range" not in caplog.text


@pytest.mark.asyncio
async def test_price_sync_rejects_groups_the_upstream_does_not_list(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(
        price_settings,
        name=f"price-bad-group-{uuid4().hex}",
        cost_multiplier="0.80",
    )
    fillable = _routed_model(provider, name=f"gpt-4o-{uuid4().hex}", upstream_model="gpt-4o")
    session.add_all([admin, provider, fillable])
    await session.flush()

    async with _api(session, price_settings, admin, _new_api_pricing_handler) as (client, _):
        response = await client.post(
            f"/admin/providers/{provider.id}/sync-model-prices",
            json={"group": "vip"},
        )

        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "invalid_price_group"

        fetched = await client.get(f"/admin/providers/{provider.id}")
        assert fetched.json()["cost_multiplier"] == "0.80"
        model = await client.get(f"/admin/models/{fillable.id}")
        assert Decimal(model.json()["input_price_per_million"]) == 0


@pytest.mark.asyncio
async def test_price_preview_lists_upstream_groups_without_writing(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(
        price_settings,
        name=f"price-preview-{uuid4().hex}",
        cost_multiplier="0.80",
    )
    fillable = _routed_model(provider, name=f"gpt-4o-{uuid4().hex}", upstream_model="gpt-4o")
    configured = _routed_model(
        provider,
        name=f"priced-{uuid4().hex}",
        upstream_model="gpt-4o",
        input_price="1.5",
        output_price="6",
    )
    fixed = _routed_model(provider, name=f"dall-e-3-{uuid4().hex}", upstream_model="dall-e-3")
    session.add_all([admin, provider, fillable, configured, fixed])
    await session.flush()

    async with _api(session, price_settings, admin, _new_api_pricing_handler) as (client, _):
        response = await client.get(f"/admin/providers/{provider.id}/upstream-pricing")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["provider_id"] == provider.id
        assert body["group_ratios"] == {"default": "2.5", "svip": "0.25"}
        # The account group is a hint only: it is not the group the relay key belongs to.
        assert body["detected_group"] == "default"
        assert body["detected_group_ratio"] == "2.5"
        assert body["upstream_models"] == 2
        assert body["fillable"] == 1
        assert body["priced"] == 1
        assert body["fixed_price"] == 1
        assert body["unlisted"] == 0

        fetched = await client.get(f"/admin/providers/{provider.id}")
        assert fetched.json()["cost_multiplier"] == "0.80"
        model = await client.get(f"/admin/models/{fillable.id}")
        assert Decimal(model.json()["input_price_per_million"]) == 0


@pytest.mark.asyncio
async def test_price_preview_reports_upstreams_without_a_pricing_endpoint(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(
        price_settings,
        name=f"price-preview-plain-{uuid4().hex}",
        base_url="https://openai.example/v1",
    )
    session.add_all([admin, provider, _routed_model(provider, name=f"plain-{uuid4().hex}")])
    await session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"}, request=request)

    async with _api(session, price_settings, admin, handler) as (client, _):
        response = await client.get(f"/admin/providers/{provider.id}/upstream-pricing")

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "model_price_sync_failed"


@pytest.mark.asyncio
async def test_model_sync_never_touches_the_cost_multiplier(
    session: AsyncSession,
    price_settings: Settings,
) -> None:
    admin = _admin(price_settings)
    provider = _provider(
        price_settings,
        name=f"price-model-sync-multiplier-{uuid4().hex}",
        cost_multiplier="0.80",
    )
    session.add_all([admin, provider])
    await session.flush()
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return _new_api_pricing_handler(request)

    async with _api(session, price_settings, admin, handler) as (client, _):
        response = await client.post(f"/admin/providers/{provider.id}/sync-models")

        assert response.status_code == 200, response.text
        assert response.json()["prices_filled"] == 1

        fetched = await client.get(f"/admin/providers/{provider.id}")
        assert fetched.json()["cost_multiplier"] == "0.80"

    # The automatic path must not probe the account group either: it can only mislead.
    assert "/api/user/self" not in paths
