from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.enums import Protocol, RequestStatus, RouteRuntimeState
from ai_gateway.db.models import (
    ApiKey,
    Model,
    ModelRoute,
    Provider,
    ProviderProtocol,
    RequestLog,
    User,
)


@pytest_asyncio.fixture
async def seeded_dashboard_data(
    session: AsyncSession,
    regular_user_record: User,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    active_key = ApiKey(
        user_id=regular_user_record.id,
        name="active-dashboard-key",
        key_prefix="sk-gw-dash-a",
        key_hash=sha256(b"active-dashboard-key").digest(),
        is_active=True,
    )
    inactive_key = ApiKey(
        user_id=regular_user_record.id,
        name="inactive-dashboard-key",
        key_prefix="sk-gw-dash-i",
        key_hash=sha256(b"inactive-dashboard-key").digest(),
        is_active=False,
    )
    providers = [
        Provider(name="dashboard-enabled", credential_encrypted=b"one", enabled=True),
        Provider(name="dashboard-disabled", credential_encrypted=b"two", enabled=False),
    ]
    models = [
        Model(canonical_name="dashboard-model-a", display_name="Dashboard A", enabled=True),
        Model(canonical_name="dashboard-model-b", display_name="Dashboard B", enabled=False),
    ]
    session.add_all([active_key, inactive_key, *providers, *models])
    await session.flush()

    protocols = [
        ProviderProtocol(
            provider_id=providers[0].id,
            protocol=Protocol.OPENAI,
            base_url="https://dashboard-one.invalid/v1",
        ),
        ProviderProtocol(
            provider_id=providers[1].id,
            protocol=Protocol.CLAUDE,
            base_url="https://dashboard-two.invalid",
        ),
    ]
    session.add_all(protocols)
    await session.flush()

    routes = [
        ModelRoute(
            model_id=models[0].id,
            provider_id=providers[0].id,
            provider_protocol_id=protocols[0].id,
            upstream_model="dashboard-upstream-a",
            enabled=True,
            runtime_state=RouteRuntimeState.CLOSED,
        ),
        ModelRoute(
            model_id=models[0].id,
            provider_id=providers[1].id,
            provider_protocol_id=protocols[1].id,
            upstream_model="dashboard-upstream-b",
            enabled=True,
            runtime_state=RouteRuntimeState.OPEN,
        ),
        ModelRoute(
            model_id=models[1].id,
            provider_id=providers[0].id,
            provider_protocol_id=protocols[0].id,
            upstream_model="dashboard-upstream-c",
            enabled=False,
            runtime_state=RouteRuntimeState.HALF_OPEN,
        ),
    ]
    session.add_all(routes)
    await session.flush()

    recent_requests = [
        RequestLog(
            id=str(uuid4()),
            user_id=regular_user_record.id,
            inbound_protocol=Protocol.OPENAI,
            transport="http",
            stream=False,
            status=RequestStatus.COMPLETED,
            prompt_tokens=100,
            completion_tokens=10,
            cost=Decimal("0.02500000"),
            latency_ms=100,
            created_at=now - timedelta(minutes=30),
        ),
        RequestLog(
            id=str(uuid4()),
            user_id=regular_user_record.id,
            inbound_protocol=Protocol.CLAUDE,
            transport="http",
            stream=True,
            status=RequestStatus.FAILED,
            prompt_tokens=200,
            completion_tokens=20,
            cost=Decimal("0.10000000"),
            latency_ms=300,
            created_at=now - timedelta(minutes=20),
        ),
        RequestLog(
            id=str(uuid4()),
            user_id=regular_user_record.id,
            inbound_protocol=Protocol.GEMINI,
            transport="http",
            stream=False,
            status=RequestStatus.CLIENT_DISCONNECTED,
            prompt_tokens=300,
            completion_tokens=30,
            cost=Decimal("0.00000000"),
            latency_ms=None,
            created_at=now - timedelta(minutes=10),
        ),
    ]
    older_daily_request = RequestLog(
        id=str(uuid4()),
        user_id=regular_user_record.id,
        inbound_protocol=Protocol.OPENAI,
        transport="http",
        stream=False,
        status=RequestStatus.FAILED,
        prompt_tokens=999,
        completion_tokens=999,
        cost=Decimal("9.00000000"),
        latency_ms=999,
        created_at=now - timedelta(days=2),
    )
    outside_daily_window = RequestLog(
        id=str(uuid4()),
        user_id=regular_user_record.id,
        inbound_protocol=Protocol.OPENAI,
        transport="http",
        stream=False,
        status=RequestStatus.FAILED,
        prompt_tokens=999,
        completion_tokens=999,
        cost=Decimal("9.00000000"),
        latency_ms=999,
        created_at=now - timedelta(days=8),
    )
    session.add_all([*recent_requests, older_daily_request, outside_daily_window])
    await session.flush()


async def test_dashboard_summary_requires_admin(non_admin_client: AsyncClient) -> None:
    response = await non_admin_client.get("/admin/dashboard/summary")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_required"


async def test_dashboard_summary_returns_counts_and_seven_utc_days(
    admin_client: AsyncClient,
    seeded_dashboard_data: None,
) -> None:
    response = await admin_client.get("/admin/dashboard/summary")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["users_total"] == 2
    assert payload["active_api_keys"] == 1
    assert payload["providers"] == {"total": 2, "enabled": 1}
    assert payload["models"] == {"total": 2, "enabled": 1}
    assert payload["routes"] == {"total": 3, "enabled": 2, "unavailable": 1}
    assert payload["requests_24h"] == 3
    assert payload["failed_requests_24h"] == 1
    assert payload["prompt_tokens_24h"] == 600
    assert payload["completion_tokens_24h"] == 60
    assert payload["cost_24h"] == "0.12500000"
    assert payload["average_latency_ms_24h"] == 200

    daily_usage = payload["daily_usage"]
    assert len(daily_usage) == 7
    assert [point["date"] for point in daily_usage] == sorted(
        point["date"] for point in daily_usage
    )
    assert daily_usage[-1]["requests"] == 3
    assert daily_usage[-1]["failures"] == 1
    assert daily_usage[-1]["cost"] == "0.12500000"
    assert sum(point["requests"] for point in daily_usage) == 4
    assert sum(point["failures"] for point in daily_usage) == 2
    assert any(
        point
        == {
            "date": point["date"],
            "requests": 0,
            "failures": 0,
            "cost": "0",
        }
        for point in daily_usage
    )


async def test_dashboard_summary_is_in_openapi(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/openapi.json")

    assert response.status_code == 200
    assert "/admin/dashboard/summary" in response.json()["paths"]
