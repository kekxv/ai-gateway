from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import httpx
import orjson
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ai_gateway.audit.service import RequestContext, RequestFailure, RequestResult
from ai_gateway.billing.service import BalanceReservation, SettlementResult
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import ApiKeyScope, Protocol
from ai_gateway.core.security import encrypt_secret
from ai_gateway.db.models import (
    ApiKey,
    Model,
    ModelAlias,
    ModelRoute,
    Provider,
    ProviderProtocol,
    User,
)
from ai_gateway.gateway.dependencies import get_gateway_service
from ai_gateway.gateway.openai import router as openai_router
from ai_gateway.gateway.service import GatewayService, is_retryable_failure
from ai_gateway.routing.service import Router


@dataclass
class FakeBilling:
    async def reserve_balance(self, **kwargs: Any) -> BalanceReservation:
        return BalanceReservation(
            ledger_entry_id=1,
            account_id=1,
            user_id=kwargs["user_id"],
            request_id=str(kwargs["request_id"]),
            idempotency_key=kwargs["idempotency_key"],
            amount=Decimal("1"),
            balance_after=Decimal("9"),
        )

    async def settle_request(self, **kwargs: Any) -> SettlementResult:
        cost = kwargs.get("cost", Decimal("0"))
        return SettlementResult(
            account_id=1,
            request_id="request",
            reserved_amount=Decimal("1"),
            actual_cost=cost,
            charged_amount=cost,
            balance=Decimal("9"),
            total_spent=cost,
            exhausted=False,
        )


@dataclass
class FakeAudit:
    completed: RequestResult | None = None
    failed: RequestFailure | None = None

    async def start_request(self, _: RequestContext, __: bytes) -> UUID:
        return uuid4()

    async def complete_request(self, _: UUID, result: RequestResult) -> None:
        self.completed = result

    async def fail_request(self, _: UUID, failure: RequestFailure) -> None:
        self.failed = failure


class FakeHttpClients:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def client_for(self, _: str | httpx.URL) -> httpx.AsyncClient:
        return self.client


def test_failover_retries_only_intended_statuses_and_transport_failures() -> None:
    assert is_retryable_failure(status_code=408)
    assert is_retryable_failure(status_code=429)
    assert is_retryable_failure(status_code=500)
    assert is_retryable_failure(status_code=599)
    assert not is_retryable_failure(status_code=400)
    assert not is_retryable_failure(status_code=401)
    assert is_retryable_failure(exception=httpx.ConnectError("offline"))
    assert is_retryable_failure(exception=httpx.ReadTimeout("slow"))
    assert not is_retryable_failure(exception=ValueError("bad request"))


async def test_mysql_backed_failover_uses_each_route_once_and_audits_attempt_order(
    test_engine: AsyncEngine,
) -> None:
    suffix = uuid4().hex
    raw_key = f"sk-gw-failover-{suffix}"
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=test_engine.url.render_as_string(hide_password=False),
        jwt_secret="gateway-failover-jwt-secret",
        encryption_key=Fernet.generate_key().decode(),
    )
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as setup:
        user = User(email=f"failover-{suffix}@example.com", password_hash="unused")
        user.api_keys.append(
            ApiKey(
                name="failover",
                key_prefix=raw_key[:12],
                key_hash=sha256(raw_key.encode()).digest(),
                scope=ApiKeyScope.ALL,
            )
        )
        model = Model(
            canonical_name=f"canonical-{suffix}",
            display_name="Failover",
            input_price_per_million=Decimal("0.1"),
            output_price_per_million=Decimal("0.2"),
        )
        alias = ModelAlias(alias=f"alias-{suffix}")
        model.aliases.append(alias)
        encrypted = encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        )
        first_provider = Provider(name=f"first-{suffix}", credential_encrypted=encrypted)
        second_provider = Provider(name=f"second-{suffix}", credential_encrypted=encrypted)
        first_protocol = ProviderProtocol(
            protocol=Protocol.OPENAI,
            base_url=f"https://first-{suffix}.example/v1",
        )
        second_protocol = ProviderProtocol(
            protocol=Protocol.OPENAI,
            base_url=f"https://second-{suffix}.example/v1",
        )
        first_provider.protocols.append(first_protocol)
        second_provider.protocols.append(second_protocol)
        setup.add_all((user, model, first_provider, second_provider))
        await setup.flush()
        first_route = ModelRoute(
            model_id=model.id,
            provider_id=first_provider.id,
            provider_protocol_id=first_protocol.id,
            upstream_model="first-native",
            weight=10000,
        )
        second_route = ModelRoute(
            model_id=model.id,
            provider_id=second_provider.id,
            provider_protocol_id=second_protocol.id,
            upstream_model="second-native",
            weight=1,
        )
        setup.add_all((first_route, second_route))
        await setup.commit()
        first_route_id = first_route.id
        second_route_id = second_route.id
        alias_name = alias.alias

    seen_models: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = orjson.loads(request.content)
        seen_models.append(payload["model"])
        if request.url.host and request.url.host.startswith("first-"):
            return httpx.Response(503, json={"error": {"message": "temporary"}})
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_failover",
                "object": "chat.completion",
                "model": "second-native",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    async with session_factory() as gateway_session:
        service = GatewayService(
            session=gateway_session,
            settings=settings,
            billing_service=FakeBilling(),  # type: ignore[arg-type]
            audit_service=audit,  # type: ignore[arg-type]
            http_client_factory=FakeHttpClients(upstream_client),
            router_factory=lambda session: Router(session, rng=random.Random(1)),
        )
        app = FastAPI()
        app.include_router(openai_router)
        app.dependency_overrides[get_gateway_service] = lambda: service
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"authorization": f"Bearer {raw_key}"},
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": alias_name,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 8,
                },
            )
    await upstream_client.aclose()

    assert response.status_code == 200, response.text
    assert seen_models == ["first-native", "second-native"]
    assert audit.completed is not None
    attempts = audit.completed.metadata["attempts"]
    assert [attempt["route_id"] for attempt in attempts] == [first_route_id, second_route_id]
    assert audit.completed.model_route_id == second_route_id
    async with session_factory() as verify:
        refreshed_first = await verify.get(ModelRoute, first_route_id)
        refreshed_second = await verify.get(ModelRoute, second_route_id)
        assert refreshed_first is not None
        assert refreshed_second is not None
        assert refreshed_first.consecutive_failures == 1
        assert refreshed_first.last_error_code == "http_503"
        assert refreshed_second.consecutive_failures == 0
