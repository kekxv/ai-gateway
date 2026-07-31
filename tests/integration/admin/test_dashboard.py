from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, time, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.admin.dashboard import dashboard_now
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol, RequestStatus, RouteRuntimeState
from ai_gateway.core.security import issue_access_token
from ai_gateway.db.models import (
    ApiKey,
    Model,
    ModelRoute,
    Provider,
    ProviderProtocol,
    RequestLog,
    User,
)
from ai_gateway.db.session import get_session
from ai_gateway.main import create_app

FIXED_NOW = datetime(2026, 7, 22, 12, 0, 0)


@pytest_asyncio.fixture
async def dashboard_admin_client(
    session: AsyncSession,
    admin_settings: Settings,
    admin_user_record: User,
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: admin_settings
    app.dependency_overrides[dashboard_now] = lambda: FIXED_NOW
    token = issue_access_token(user_id=admin_user_record.id, settings=admin_settings)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client


def _request_log(
    *,
    user_id: int,
    created_at: datetime,
    status: RequestStatus,
    prompt_tokens: int,
    completion_tokens: int,
    cost: str,
    latency_ms: int | None,
    cost_amount: str = "0",
) -> RequestLog:
    return RequestLog(
        id=str(uuid4()),
        user_id=user_id,
        inbound_protocol=Protocol.OPENAI,
        transport="http",
        stream=False,
        status=status,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=Decimal(cost),
        cost_amount=Decimal(cost_amount),
        latency_ms=latency_ms,
        created_at=created_at,
    )


@pytest_asyncio.fixture
async def seeded_dashboard_data(
    session: AsyncSession,
    regular_user_record: User,
) -> None:
    expired_but_active_key = ApiKey(
        user_id=regular_user_record.id,
        name="expired-but-active-dashboard-key",
        key_prefix="sk-gw-dash-a",
        key_hash=sha256(b"active-dashboard-key").digest(),
        is_active=True,
        expires_at=FIXED_NOW - timedelta(days=1),
    )
    unexpired_but_inactive_key = ApiKey(
        user_id=regular_user_record.id,
        name="unexpired-but-inactive-dashboard-key",
        key_prefix="sk-gw-dash-i",
        key_hash=sha256(b"inactive-dashboard-key").digest(),
        is_active=False,
        expires_at=FIXED_NOW + timedelta(days=1),
    )
    providers = [
        Provider(name="dashboard-enabled", credential_encrypted=b"one", enabled=True),
        Provider(name="dashboard-disabled", credential_encrypted=b"two", enabled=False),
    ]
    models = [
        Model(canonical_name="dashboard-model-a", display_name="Dashboard A", enabled=True),
        Model(canonical_name="dashboard-model-b", display_name="Dashboard B", enabled=False),
    ]
    session.add_all([expired_but_active_key, unexpired_but_inactive_key, *providers, *models])
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

    session.add_all(
        [
            ModelRoute(
                model_id=models[0].id,
                provider_id=providers[0].id,
                upstream_model="dashboard-upstream-a",
                enabled=True,
                runtime_state=RouteRuntimeState.CLOSED,
            ),
            ModelRoute(
                model_id=models[0].id,
                provider_id=providers[1].id,
                upstream_model="dashboard-upstream-b",
                enabled=True,
                runtime_state=RouteRuntimeState.OPEN,
            ),
            ModelRoute(
                model_id=models[1].id,
                provider_id=providers[0].id,
                upstream_model="dashboard-upstream-c",
                enabled=False,
                runtime_state=RouteRuntimeState.HALF_OPEN,
            ),
        ]
    )

    cutoff_24h = FIXED_NOW - timedelta(hours=24)
    first_daily_midnight = datetime.combine(
        FIXED_NOW.date() - timedelta(days=6),
        time.min,
    )
    session.add_all(
        [
            _request_log(
                user_id=regular_user_record.id,
                created_at=cutoff_24h,
                status=RequestStatus.COMPLETED,
                prompt_tokens=10,
                completion_tokens=1,
                cost="0.01000000",
                latency_ms=100,
            ),
            _request_log(
                user_id=regular_user_record.id,
                created_at=cutoff_24h + timedelta(seconds=1),
                status=RequestStatus.FAILED,
                prompt_tokens=20,
                completion_tokens=2,
                cost="0.02000000",
                latency_ms=200,
            ),
            _request_log(
                user_id=regular_user_record.id,
                created_at=cutoff_24h - timedelta(seconds=1),
                status=RequestStatus.FAILED,
                prompt_tokens=40,
                completion_tokens=4,
                cost="0.04000000",
                latency_ms=400,
            ),
            _request_log(
                user_id=regular_user_record.id,
                created_at=FIXED_NOW - timedelta(minutes=30),
                status=RequestStatus.COMPLETED,
                prompt_tokens=100,
                completion_tokens=10,
                cost="0.02500000",
                latency_ms=100,
            ),
            _request_log(
                user_id=regular_user_record.id,
                created_at=FIXED_NOW - timedelta(minutes=20),
                status=RequestStatus.FAILED,
                prompt_tokens=200,
                completion_tokens=20,
                cost="0.10000000",
                cost_amount="0.05000000",
                latency_ms=300,
            ),
            _request_log(
                user_id=regular_user_record.id,
                created_at=FIXED_NOW - timedelta(minutes=10),
                status=RequestStatus.CLIENT_DISCONNECTED,
                prompt_tokens=300,
                completion_tokens=30,
                cost="0.00000000",
                latency_ms=None,
            ),
            _request_log(
                user_id=regular_user_record.id,
                created_at=FIXED_NOW,
                status=RequestStatus.COMPLETED,
                prompt_tokens=5,
                completion_tokens=5,
                cost="0.00500000",
                latency_ms=500,
            ),
            _request_log(
                user_id=regular_user_record.id,
                created_at=FIXED_NOW + timedelta(seconds=1),
                status=RequestStatus.FAILED,
                prompt_tokens=1000,
                completion_tokens=1000,
                cost="10.00000000",
                latency_ms=1000,
            ),
            _request_log(
                user_id=regular_user_record.id,
                created_at=first_daily_midnight,
                status=RequestStatus.COMPLETED,
                prompt_tokens=500,
                completion_tokens=500,
                cost="0.50000000",
                latency_ms=500,
            ),
            _request_log(
                user_id=regular_user_record.id,
                created_at=first_daily_midnight - timedelta(seconds=1),
                status=RequestStatus.FAILED,
                prompt_tokens=1000,
                completion_tokens=1000,
                cost="10.00000000",
                latency_ms=1000,
            ),
        ]
    )
    await session.flush()


async def test_dashboard_summary_requires_admin(non_admin_client: AsyncClient) -> None:
    response = await non_admin_client.get("/admin/dashboard/summary")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_required"


async def test_dashboard_summary_returns_counts_and_exact_seven_utc_days(
    dashboard_admin_client: AsyncClient,
    seeded_dashboard_data: None,
) -> None:
    response = await dashboard_admin_client.get("/admin/dashboard/summary")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["users_total"] == 2
    # The brief defines active API keys by the persisted is_active flag only.
    assert payload["active_api_keys"] == 1
    assert payload["providers"] == {"total": 2, "enabled": 1}
    assert payload["models"] == {"total": 2, "enabled": 1}
    assert payload["routes"] == {"total": 3, "enabled": 2, "unavailable": 1}

    # Exact cutoff and exact now are included; one second outside either bound is excluded.
    assert payload["requests_24h"] == 6
    assert payload["failed_requests_24h"] == 2
    assert payload["prompt_tokens_24h"] == 635
    assert payload["completion_tokens_24h"] == 68
    assert payload["cache_read_tokens_24h"] == 0
    assert payload["cache_write_tokens_24h"] == 0
    assert payload["total_tokens_24h"] == 703
    assert payload["cost_24h"] == "0.16000000"
    assert payload["cost_amount_24h"] == "0.05000000"
    assert payload["gross_profit_24h"] == "0.11000000"
    assert payload["average_latency_ms_24h"] == 240

    # All-time totals
    assert payload["total_requests"] == 10
    assert payload["total_prompt_tokens"] == 3175
    assert payload["total_completion_tokens"] == 2572

    daily_usage = payload["daily_usage"]
    expected_dates = [
        (FIXED_NOW.date() - timedelta(days=6) + timedelta(days=offset)).isoformat()
        for offset in range(7)
    ]
    assert [point["date"] for point in daily_usage] == expected_dates
    # Midnight on today-6 is included, while the record one second before it is excluded.
    assert daily_usage[0] == {
        "date": expected_dates[0],
        "requests": 1,
        "failures": 0,
        "cost": "0.50000000",
        "cost_amount": "0E-8",
        "gross_profit": "0.50000000",
    }
    assert daily_usage[-2] == {
        "date": expected_dates[-2],
        "requests": 3,
        "failures": 2,
        "cost": "0.07000000",
        "cost_amount": "0E-8",
        "gross_profit": "0.07000000",
    }
    assert daily_usage[-1] == {
        "date": expected_dates[-1],
        "requests": 4,
        "failures": 1,
        "cost": "0.13000000",
        "cost_amount": "0.05000000",
        "gross_profit": "0.08000000",
    }
    assert all(
        point["requests"] == point["failures"] == 0 and point["cost"] == "0"
        for point in daily_usage[1:-2]
    )
    assert sum(point["requests"] for point in daily_usage) == 8
    assert sum(point["failures"] for point in daily_usage) == 3


async def test_dashboard_summary_openapi_contract(
    dashboard_admin_client: AsyncClient,
) -> None:
    response = await dashboard_admin_client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    success_schema = document["paths"]["/admin/dashboard/summary"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert success_schema == {"$ref": "#/components/schemas/DashboardSummary"}

    summary_schema = document["components"]["schemas"]["DashboardSummary"]
    required_fields = {
        "users_total",
        "active_api_keys",
        "providers",
        "models",
        "routes",
        "requests_24h",
        "failed_requests_24h",
        "prompt_tokens_24h",
        "completion_tokens_24h",
        "cache_read_tokens_24h",
        "cache_write_tokens_24h",
        "total_tokens_24h",
        "cost_24h",
        "cost_amount_24h",
        "gross_profit_24h",
        "average_latency_ms_24h",
        "total_requests",
        "total_cost",
        "total_cost_amount",
        "total_gross_profit",
        "total_prompt_tokens",
        "total_completion_tokens",
        "daily_usage",
        "top_models",
    }
    assert required_fields <= set(summary_schema["properties"])
    assert required_fields <= set(summary_schema["required"])
