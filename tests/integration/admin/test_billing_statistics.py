from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.enums import Protocol, RequestStatus
from ai_gateway.core.security import hash_password
from ai_gateway.db.models import Account, ApiKey, Model, Provider, RequestLog, User


async def test_billing_statistics_scopes_regular_users_and_hides_internal_financials(
    admin_client: AsyncClient,
    non_admin_client: AsyncClient,
    session: AsyncSession,
    regular_user_record: User,
) -> None:
    other_user = User(
        email="billing-other@example.com",
        password_hash=hash_password("other-user-password"),
        role="user",
    )
    other_user.account = Account()
    provider_a = Provider(name="billing-provider-a", credential_encrypted=b"provider-a")
    provider_b = Provider(name="billing-provider-b", credential_encrypted=b"provider-b")
    model = Model(canonical_name="billing-model", display_name="Billing Model")
    session.add_all([other_user, provider_a, provider_b, model])
    await session.flush()

    own_key = ApiKey(
        user_id=regular_user_record.id,
        name="billing-own-key",
        key_prefix="sk-bill-own",
        key_hash=sha256(b"billing-own-key").digest(),
    )
    other_key = ApiKey(
        user_id=other_user.id,
        name="billing-other-key",
        key_prefix="sk-bill-oth",
        key_hash=sha256(b"billing-other-key").digest(),
    )
    session.add_all([own_key, other_key])
    await session.flush()

    session.add_all(
        [
            RequestLog(
                id=str(uuid4()),
                user_id=regular_user_record.id,
                api_key_id=own_key.id,
                model_id=model.id,
                provider_id=provider_a.id,
                inbound_protocol=Protocol.OPENAI,
                transport="http",
                stream=False,
                status=RequestStatus.COMPLETED,
                prompt_tokens=10,
                completion_tokens=2,
                cache_read_tokens=3,
                cache_write_tokens=4,
                cost=Decimal("0.10000000"),
                cost_amount=Decimal("0.04000000"),
                latency_ms=100,
                created_at=datetime(2026, 7, 20, 12, 0, 0),
            ),
            RequestLog(
                id=str(uuid4()),
                user_id=regular_user_record.id,
                api_key_id=own_key.id,
                model_id=model.id,
                provider_id=provider_b.id,
                inbound_protocol=Protocol.OPENAI,
                transport="http",
                stream=False,
                status=RequestStatus.FAILED,
                prompt_tokens=20,
                completion_tokens=4,
                cache_read_tokens=5,
                cache_write_tokens=6,
                cost=Decimal("0.20000000"),
                cost_amount=Decimal("0.10000000"),
                latency_ms=200,
                created_at=datetime(2026, 7, 22, 12, 0, 0),
            ),
            RequestLog(
                id=str(uuid4()),
                user_id=other_user.id,
                api_key_id=other_key.id,
                model_id=model.id,
                provider_id=provider_a.id,
                inbound_protocol=Protocol.OPENAI,
                transport="http",
                stream=False,
                status=RequestStatus.COMPLETED,
                prompt_tokens=900,
                completion_tokens=900,
                cost=Decimal("9.00000000"),
                cost_amount=Decimal("8.00000000"),
                latency_ms=900,
                created_at=datetime(2026, 7, 21, 12, 0, 0),
            ),
            RequestLog(
                id=str(uuid4()),
                user_id=regular_user_record.id,
                api_key_id=own_key.id,
                model_id=model.id,
                provider_id=provider_a.id,
                inbound_protocol=Protocol.OPENAI,
                transport="http",
                stream=False,
                status=RequestStatus.COMPLETED,
                prompt_tokens=1_000,
                completion_tokens=1_000,
                cost=Decimal("10.00000000"),
                cost_amount=Decimal("9.00000000"),
                latency_ms=1_000,
                created_at=datetime(2026, 7, 23, 0, 0, 0),
            ),
        ]
    )
    await session.flush()

    base_params = [
        ("start_at", "2026-07-20T00:00:00Z"),
        ("end_at", "2026-07-22T23:59:59Z"),
        ("model_ids", str(model.id)),
        ("api_key_ids", str(own_key.id)),
    ]
    admin_response = await admin_client.get(
        "/admin/billing-statistics",
        params=[
            *base_params,
            ("provider_ids", str(provider_a.id)),
            ("provider_ids", str(provider_b.id)),
        ],
    )
    assert admin_response.status_code == 200, admin_response.text
    admin_payload = admin_response.json()
    assert admin_payload["totals"] == {
        "requests": 2,
        "failed_requests": 1,
        "prompt_tokens": 30,
        "completion_tokens": 6,
        "cache_read_tokens": 8,
        "cache_write_tokens": 10,
        "user_cost": "0.30000000",
        "cost_amount": "0.14000000",
        "gross_profit": "0.16000000",
        "average_latency_ms": 150,
    }
    assert [point["date"] for point in admin_payload["daily_usage"]] == [
        "2026-07-20",
        "2026-07-21",
        "2026-07-22",
    ]
    assert admin_payload["daily_usage"][1]["requests"] == 0
    assert {row["name"] for row in admin_payload["provider_stats"]} == {
        "billing-provider-a",
        "billing-provider-b",
    }

    forbidden = await non_admin_client.get(
        "/admin/billing-statistics",
        params=base_params,
    )
    assert forbidden.status_code == 403

    user_response = await non_admin_client.get(
        "/user/billing-statistics",
        params=[
            ("start_at", "2026-07-20T00:00:00Z"),
            ("end_at", "2026-07-22T23:59:59Z"),
            ("model_ids", str(model.id)),
        ],
    )
    assert user_response.status_code == 200, user_response.text
    user_payload = user_response.json()
    assert user_payload["totals"] == {
        "requests": 2,
        "failed_requests": 1,
        "prompt_tokens": 30,
        "completion_tokens": 6,
        "cache_read_tokens": 8,
        "cache_write_tokens": 10,
        "user_cost": "0.30000000",
        "average_latency_ms": 150,
    }
    assert "cost_amount" not in user_payload["totals"]
    assert "gross_profit" not in user_payload["totals"]
    assert "provider_stats" not in user_payload
    assert user_payload["api_key_stats"] == [
        {
            "id": own_key.id,
            "name": "billing-own-key",
            "requests": 2,
            "failed_requests": 1,
            "prompt_tokens": 30,
            "completion_tokens": 6,
            "cache_read_tokens": 8,
            "cache_write_tokens": 10,
            "user_cost": "0.30000000",
            "average_latency_ms": 150,
        }
    ]


async def test_billing_statistics_rejects_naive_or_reversed_ranges(
    admin_client: AsyncClient,
) -> None:
    naive = await admin_client.get(
        "/admin/billing-statistics",
        params={"start_at": "2026-07-20T00:00:00", "end_at": "2026-07-20T01:00:00Z"},
    )
    reversed_range = await admin_client.get(
        "/admin/billing-statistics",
        params={"start_at": "2026-07-21T00:00:00Z", "end_at": "2026-07-20T00:00:00Z"},
    )

    assert naive.status_code == 422
    assert reversed_range.status_code == 422
