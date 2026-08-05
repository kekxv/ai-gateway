from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import httpx
import orjson
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.audit.service import RequestContext, RequestFailure, RequestResult
from ai_gateway.auth.api_key import ApiKeyPrincipal
from ai_gateway.billing.service import (
    BalanceReservation,
    InsufficientBalance,
    ReservationRecovery,
    SettlementResult,
)
from ai_gateway.catalog.repository import ModelNotFound
from ai_gateway.catalog.schemas import ResolvedModel
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import ApiKeyScope, Protocol, RouteRuntimeState
from ai_gateway.core.security import encrypt_secret
from ai_gateway.db.models import ApiKey, Model, ModelAlias, User
from ai_gateway.gateway.claude import router as claude_router
from ai_gateway.gateway.dependencies import get_gateway_service
from ai_gateway.gateway.gemini import router as gemini_router
from ai_gateway.gateway.openai import router as openai_router
from ai_gateway.gateway.service import (
    GatewayService,
    UpstreamError,
    UpstreamTimeout,
    _billing_key,
    native_error_response,
    upstream_url,
)
from ai_gateway.protocols.base import UnsupportedFeatureError
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.routing.types import NoRouteAvailable, RouteCandidate

RAW_KEY = "sk-gw-contract-key-123456789"


@dataclass
class FakeBilling:
    reservation: BalanceReservation = BalanceReservation(
        ledger_entry_id=1,
        account_id=1,
        user_id=1,
        request_id="request",
        idempotency_key="key",
        amount=Decimal("1"),
        balance_after=Decimal("9"),
    )
    settlements: int = 0
    reservation_keys: list[str] = field(default_factory=list)
    reservation_recoveries: list[ReservationRecovery] = field(default_factory=list)
    recovery_updates: list[ReservationRecovery] = field(default_factory=list)
    reserved_models: list[Model] = field(default_factory=list)
    settled_models: list[Model] = field(default_factory=list)
    reservation_public_multipliers: list[Decimal | None] = field(default_factory=list)

    async def reserve_balance(self, **kwargs: Any) -> BalanceReservation:
        self.reservation_keys.append(kwargs["idempotency_key"])
        self.reservation_recoveries.append(kwargs["recovery"])
        self.reserved_models.append(kwargs["model"])
        self.reservation_public_multipliers.append(kwargs.get("provider_public_multiplier"))
        return self.reservation

    async def update_reservation_recovery(self, **kwargs: Any) -> bool:
        self.recovery_updates.append(kwargs["recovery"])
        return True

    async def settle_request(self, **kwargs: Any) -> SettlementResult:
        self.settlements += 1
        if "model" in kwargs:
            self.settled_models.append(kwargs["model"])
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
    started: RequestContext | None = None

    async def start_request(
        self,
        context: RequestContext,
        __: bytes,
        *,
        request_id: UUID | None = None,
    ) -> UUID:
        self.started = context
        return request_id or uuid4()

    async def complete_request(self, _: UUID, result: RequestResult) -> None:
        self.completed = result

    async def fail_request(self, _: UUID, failure: RequestFailure) -> None:
        self.failed = failure


class FakeRouter:
    def __init__(self, routes: list[RouteCandidate]) -> None:
        self.routes = routes
        self.successes: list[int] = []
        self.failures: list[int] = []
        self.selections: list[ResolvedModel | int] = []
        self.eligibility_checks: list[ResolvedModel | int] = []
        self.multiplier_model_ids: list[int] = []

    async def select_route(
        self,
        model: ResolvedModel | int,
        __: Any,
        required_protocol: Protocol | str | None = None,
        *,
        preferred_protocol: Protocol | str | None = None,
        requested_model: str | None = None,
        excluded_route_ids: frozenset[int] | set[int] = frozenset(),
    ) -> RouteCandidate:
        del required_protocol, preferred_protocol
        self.selections.append(model)
        model_ids = model.model_ids if isinstance(model, ResolvedModel) else (model,)
        for route in self.routes:
            if route.model_id in model_ids and route.route_id not in excluded_route_ids:
                return route
        requested_name = (
            model.requested_name if isinstance(model, ResolvedModel) else requested_model
        )
        raise NoRouteAvailable(requested_name or str(model))

    async def record_success(self, route_id: int) -> bool:
        self.successes.append(route_id)
        return True

    async def record_failure(self, route_id: int, _: object) -> bool:
        self.failures.append(route_id)
        return True

    async def has_eligible_route(
        self,
        model: ResolvedModel | int,
        __: Any,
        required_protocol: Protocol | str | None = None,
    ) -> bool:
        del required_protocol
        self.eligibility_checks.append(model)
        model_ids = model.model_ids if isinstance(model, ResolvedModel) else (model,)
        return any(route.model_id in model_ids for route in self.routes)

    async def maximum_eligible_public_multiplier(
        self,
        model_id: int,
        _: Any,
        required_protocol: Protocol | str | None = None,
        *,
        require_websocket: bool = False,
    ) -> None:
        del required_protocol, require_websocket
        self.multiplier_model_ids.append(model_id)


class FakeHttpClients:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def client_for(self, _: str | httpx.URL) -> httpx.AsyncClient:
        return self.client


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret="gateway-contract-jwt-secret",
        encryption_key=Fernet.generate_key().decode(),
    )


async def _catalog(session: AsyncSession) -> Model:
    user = User(email=f"gateway-{uuid4()}@example.com", password_hash="unused")
    user.api_keys.append(
        ApiKey(
            name="contract",
            key_prefix=RAW_KEY[:12],
            key_hash=sha256(RAW_KEY.encode()).digest(),
            scope=ApiKeyScope.ALL,
        )
    )
    model = Model(
        canonical_name=f"canonical-{uuid4()}",
        display_name="Gateway Contract",
        input_price_per_million=Decimal("0.1"),
        output_price_per_million=Decimal("0.2"),
    )
    model.aliases.append(ModelAlias(alias=f"alias-{uuid4()}"))
    session.add_all((user, model))
    await session.flush()
    return model


async def _shared_catalog(session: AsyncSession) -> tuple[str, Model, Model]:
    model_a = await _catalog(session)
    alias = model_a.aliases[0].alias
    model_b = Model(
        canonical_name=f"canonical-b-{uuid4()}",
        display_name="Gateway Contract B",
        input_price_per_million=Decimal("9.1"),
        output_price_per_million=Decimal("9.2"),
    )
    model_b.aliases.append(ModelAlias(alias=alias))
    session.add(model_b)
    await session.flush()
    return alias, model_a, model_b


def _request(protocol: Protocol, model: str) -> tuple[str, dict[str, Any]]:
    if protocol is Protocol.OPENAI:
        return "/v1/chat/completions", {
            "model": model,
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
        }
    if protocol is Protocol.CLAUDE:
        return "/v1/messages", {
            "model": model,
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
        }
    return f"/v1beta/models/{model}:generateContent", {
        "contents": [{"role": "user", "parts": [{"text": "hello"}]}],
        "generationConfig": {"maxOutputTokens": 8},
    }


def _response(protocol: Protocol, model: str) -> dict[str, Any]:
    if protocol is Protocol.OPENAI:
        return {
            "id": "chatcmpl_gateway",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "world"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 2,
                "prompt_tokens_details": {
                    "cached_tokens": 1,
                    "cache_write_tokens": 1,
                },
            },
        }
    if protocol is Protocol.CLAUDE:
        return {
            "id": "msg_gateway",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": "world"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": 3,
                "output_tokens": 2,
                "cache_read_input_tokens": 1,
                "cache_creation_input_tokens": 1,
            },
        }
    return {
        "modelVersion": model,
        "responseId": "response_gateway",
        "candidates": [
            {
                "index": 0,
                "content": {"role": "model", "parts": [{"text": "world"}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 4,
            "candidatesTokenCount": 2,
            "cachedContentTokenCount": 1,
        },
    }


def _app(service: GatewayService) -> FastAPI:
    app = FastAPI()
    app.include_router(openai_router)
    app.include_router(claude_router)
    app.include_router(gemini_router)
    app.dependency_overrides[get_gateway_service] = lambda: service
    return app


@pytest.mark.parametrize(
    "path",
    [
        "/v1/messages/count_tokens?beta=true",
        "/anthropic/v1/messages/count_tokens",
    ],
)
async def test_claude_count_tokens_authenticates_and_counts_locally_without_billing_or_upstream(
    session: AsyncSession,
    path: str,
) -> None:
    settings = _settings()
    alias, _, model_b = await _shared_catalog(session)
    route = RouteCandidate(
        route_id=141,
        model_id=model_b.id,
        provider_id=142,
        provider_protocol_id=143,
        protocol=Protocol.CLAUDE,
        base_url="https://provider.example",
        websocket_url=None,
        upstream_model="claude-native",
        weight=100,
    )
    upstream_calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal upstream_calls
        upstream_calls += 1
        return httpx.Response(500)

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    billing = FakeBilling()
    audit = FakeAudit()
    route_router = FakeRouter([route])
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: route_router,
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"x-api-key": RAW_KEY, "anthropic-version": "2023-06-01"},
    ) as client:
        response = await client.post(
            path,
            json={
                "model": alias,
                "system": "You are concise.",
                "messages": [{"role": "user", "content": "Count this message."}],
                "tools": [
                    {
                        "name": "lookup",
                        "description": "Look up a value",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                        },
                    }
                ],
            },
        )
    await upstream_client.aclose()

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/json"
    assert set(response.json()) == {"input_tokens"}
    assert isinstance(response.json()["input_tokens"], int)
    assert response.json()["input_tokens"] > 0
    assert billing.reservation_keys == []
    assert billing.settlements == 0
    assert audit.completed is None
    assert audit.failed is None
    assert upstream_calls == 0
    assert len(route_router.eligibility_checks) == 1
    eligibility_model = route_router.eligibility_checks[0]
    assert isinstance(eligibility_model, ResolvedModel)
    assert model_b.id in eligibility_model.model_ids


async def test_claude_count_tokens_authenticates_before_parsing(session: AsyncSession) -> None:
    settings = _settings()
    await _catalog(session)
    upstream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    )
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([]),
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
    ) as client:
        response = await client.post("/v1/messages/count_tokens", content=b"{not-json")
    await upstream_client.aclose()

    assert response.status_code == 401
    assert response.json()["type"] == "error"
    assert response.json()["error"]["type"] == "invalid_api_key"


@pytest.mark.parametrize("inbound", list(Protocol))
@pytest.mark.parametrize("outbound", list(Protocol))
async def test_all_protocol_pairs_bind_alias_to_selected_upstream_model(
    session: AsyncSession,
    inbound: Protocol,
    outbound: Protocol,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    alias = model.aliases[0].alias
    upstream_model = f"native-{outbound.value}-{uuid4()}"
    route = RouteCandidate(
        route_id=11,
        model_id=model.id,
        provider_id=21,
        provider_protocol_id=31,
        protocol=outbound,
        base_url="https://provider.example",
        websocket_url=None,
        upstream_model=upstream_model,
        weight=100,
        provider_credential_encrypted=encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        ),
    )
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_response(outbound, upstream_model))

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    billing = FakeBilling()
    audit = FakeAudit()
    router = FakeRouter([route])
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    path, body = _request(inbound, alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200, response.text
    assert len(seen) == 1
    upstream_payload = orjson.loads(seen[0].content)
    if outbound is Protocol.GEMINI:
        assert "model" not in upstream_payload
        assert request_model_path(seen[0]) == upstream_model
    else:
        assert upstream_payload["model"] == upstream_model
    assert alias not in seen[0].content.decode()
    assert model.canonical_name not in seen[0].content.decode()
    decode_payload = {**upstream_payload, "model": upstream_model}
    get_adapter(outbound).decode_request(decode_payload)
    canonical_response = get_adapter(inbound).decode_response(response.json())
    assert canonical_response.message.content[0].text == "world"  # type: ignore[union-attr]
    expected_auth = {
        Protocol.OPENAI: ("authorization", "Bearer provider-secret"),
        Protocol.CLAUDE: ("x-api-key", "provider-secret"),
        Protocol.GEMINI: ("x-goog-api-key", "provider-secret"),
    }[outbound]
    assert seen[0].headers[expected_auth[0]] == expected_auth[1]
    assert RAW_KEY not in str(seen[0].headers)
    assert audit.completed is not None
    assert audit.completed.prompt_tokens == 3
    assert audit.completed.completion_tokens == 2
    assert audit.completed.cache_read_tokens == 1
    assert audit.completed.cache_write_tokens == (0 if outbound is Protocol.GEMINI else 1)
    assert billing.settlements == 1


async def test_shared_alias_selected_model_controls_http_lifecycle_and_retries(
    session: AsyncSession,
) -> None:
    settings = _settings()
    alias, model_a, model_b = await _shared_catalog(session)
    route_b_first = RouteCandidate(
        route_id=151,
        model_id=model_b.id,
        provider_id=251,
        provider_protocol_id=351,
        protocol=Protocol.OPENAI,
        base_url="https://selected-b-first.example/v1",
        websocket_url=None,
        upstream_model="native-b-first",
        weight=100,
        provider_public_multiplier=Decimal("2.75"),
        runtime_state=RouteRuntimeState.HALF_OPEN,
        provider_credential_encrypted=encrypt_secret("{}", settings=settings),
    )
    route_a = RouteCandidate(
        route_id=152,
        model_id=model_a.id,
        provider_id=252,
        provider_protocol_id=352,
        protocol=Protocol.OPENAI,
        base_url="https://unselected-a.example/v1",
        websocket_url=None,
        upstream_model="native-a",
        weight=100,
        provider_credential_encrypted=encrypt_secret("{}", settings=settings),
    )
    route_b_retry = RouteCandidate(
        route_id=153,
        model_id=model_b.id,
        provider_id=253,
        provider_protocol_id=353,
        protocol=Protocol.OPENAI,
        base_url="https://selected-b-retry.example/v1",
        websocket_url=None,
        upstream_model="native-b-retry",
        weight=100,
        provider_credential_encrypted=encrypt_secret("{}", settings=settings),
    )
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "selected-b-first.example":
            return httpx.Response(503)
        upstream_model = {
            "unselected-a.example": "native-a",
            "selected-b-retry.example": "native-b-retry",
        }[request.url.host]
        return httpx.Response(200, json=_response(Protocol.OPENAI, upstream_model))

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    billing = FakeBilling()
    audit = FakeAudit()
    route_router = FakeRouter([route_b_first, route_a, route_b_retry])
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: route_router,
    )
    path, body = _request(Protocol.OPENAI, alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200, response.text
    assert [request.url.host for request in seen] == [
        "selected-b-first.example",
        "selected-b-retry.example",
    ]
    assert [model.id for model in billing.reserved_models] == [model_b.id]
    assert [model.id for model in billing.settled_models] == [model_b.id]
    assert billing.reservation_public_multipliers == [Decimal("2.75")]
    assert route_router.multiplier_model_ids == [model_b.id]
    assert route_router.failures == [route_b_first.route_id]
    assert route_router.successes == [route_b_retry.route_id]
    assert len(route_router.selections) == 2
    assert isinstance(route_router.selections[0], ResolvedModel)
    assert route_router.selections[1] == model_b.id
    assert audit.started is not None
    assert audit.started.model_id == model_b.id
    assert audit.started.metadata == {
        "requested_model": alias,
        "canonical_model": model_b.canonical_name,
    }


async def test_openai_compatible_credentialless_route_sends_normal_upstream_request(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    route = RouteCandidate(
        route_id=111,
        model_id=model.id,
        provider_id=121,
        provider_protocol_id=131,
        protocol=Protocol.OPENAI,
        base_url="http://ollama.example/v1",
        websocket_url=None,
        upstream_model="ollama-native-model",
        weight=100,
        provider_credential_encrypted=encrypt_secret("{}", settings=settings),
    )
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_response(Protocol.OPENAI, route.upstream_model))

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([route]),
    )
    path, body = _request(Protocol.OPENAI, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200, response.text
    assert len(seen) == 1
    assert "authorization" not in seen[0].headers
    assert RAW_KEY not in str(seen[0].headers)


@pytest.mark.parametrize("protocol", list(Protocol))
async def test_same_protocol_preserves_vendor_json_and_response_bytes(
    session: AsyncSession,
    protocol: Protocol,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    alias = model.aliases[0].alias
    upstream_model = f"native-{protocol.value}"
    route = RouteCandidate(
        route_id=12,
        model_id=model.id,
        provider_id=22,
        provider_protocol_id=32,
        protocol=protocol,
        base_url="https://provider.example",
        websocket_url=None,
        upstream_model=upstream_model,
        weight=100,
        provider_credential_encrypted=encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        ),
    )
    response_bytes = orjson.dumps(_response(protocol, upstream_model))
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            201,
            content=response_bytes,
            headers={"content-type": "application/vnd.provider+json"},
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([route]),
    )
    path, body = _request(protocol, alias)
    body["vendor_unknown"] = {"nested": [1, "two"]}
    if protocol is Protocol.CLAUDE:
        body["messages"].append(
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": "native system message"},
                    {"type": "future_beta_block", "payload": {"mode": "native"}},
                ],
                "cache_control": {"type": "ephemeral"},
            }
        )
        path = f"{path}?beta=true"
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={
            "authorization": f"Bearer {RAW_KEY}",
            "connection": "keep-alive, x-remove",
            "x-remove": "secret-hop",
        },
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 201
    assert response.content == response_bytes
    assert response.headers["content-type"] == "application/vnd.provider+json"
    upstream_payload = orjson.loads(seen[0].content)
    assert upstream_payload["vendor_unknown"] == {"nested": [1, "two"]}
    if protocol is Protocol.GEMINI:
        assert "model" not in upstream_payload
        assert request_model_path(seen[0]) == upstream_model
    else:
        assert upstream_payload["model"] == upstream_model
    if protocol is Protocol.CLAUDE:
        assert upstream_payload["messages"][1] == {
            "role": "system",
            "content": [
                {"type": "text", "text": "native system message"},
                {"type": "future_beta_block", "payload": {"mode": "native"}},
            ],
            "cache_control": {"type": "ephemeral"},
        }
        assert seen[0].url.params["beta"] == "true"
    assert "x-remove" not in seen[0].headers


@pytest.mark.parametrize(
    ("protocol", "path", "expected"),
    [
        (Protocol.OPENAI, "/v1/chat/completions", "error"),
        (Protocol.CLAUDE, "/v1/messages", "type"),
        (Protocol.GEMINI, "/v1beta/models/unknown:generateContent", "error"),
    ],
)
async def test_malformed_json_returns_native_400_without_upstream(
    session: AsyncSession,
    protocol: Protocol,
    path: str,
    expected: str,
) -> None:
    settings = _settings()
    await _catalog(session)
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([]),
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(
            path,
            content=b"{not-json",
            headers={"content-type": "application/json"},
        )
    await upstream_client.aclose()

    assert response.status_code == 400
    assert expected in response.json()
    assert not called


async def test_no_route_request_is_audited(session: AsyncSession) -> None:
    settings = _settings()
    model = await _catalog(session)
    alias = model.aliases[0].alias
    upstream_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    )
    audit = FakeAudit()
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([]),
    )
    path, body = _request(Protocol.OPENAI, alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 503
    assert audit.started is not None
    assert audit.started.model_id is None
    assert audit.started.metadata["requested_model"] == alias
    assert audit.failed is not None
    assert audit.failed.error_code == "no_route_available"
    assert audit.failed.http_status == 503


def test_upstream_urls_use_native_generation_endpoints_and_route_model() -> None:
    assert (
        upstream_url(Protocol.OPENAI, "https://provider.example/v1", "native-model")
        == "https://provider.example/v1/chat/completions"
    )


def request_model_path(request: httpx.Request) -> str:
    marker = "/models/"
    encoded = request.url.raw_path.decode().split(marker, 1)[1].split(":generateContent", 1)[0]
    return httpx.URL(f"https://example.test/{encoded}").path.lstrip("/")


async def test_authentication_precedes_malformed_json(session: AsyncSession) -> None:
    settings = _settings()
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([]),
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": "Bearer sk-gw-invalid"},
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            content=b"{not-json",
            headers={"content-type": "application/json"},
        )
    await upstream_client.aclose()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"
    assert not called


async def test_missing_upstream_content_type_remains_absent(session: AsyncSession) -> None:
    settings = _settings()
    model = await _catalog(session)
    route = RouteCandidate(
        route_id=91,
        model_id=model.id,
        provider_id=92,
        provider_protocol_id=93,
        protocol=Protocol.OPENAI,
        base_url="https://provider.example",
        websocket_url=None,
        upstream_model="native-no-content-type",
        weight=100,
        provider_credential_encrypted=encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        ),
    )
    response_bytes = orjson.dumps(_response(Protocol.OPENAI, route.upstream_model))

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=response_bytes)

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([route]),
    )
    path, body = _request(Protocol.OPENAI, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.content == response_bytes
    assert "content-type" not in response.headers


async def test_same_client_idempotency_header_never_reuses_billing_key(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    route = RouteCandidate(
        route_id=94,
        model_id=model.id,
        provider_id=95,
        provider_protocol_id=96,
        protocol=Protocol.OPENAI,
        base_url="https://provider.example",
        websocket_url=None,
        upstream_model="native-billing-key",
        weight=100,
        provider_credential_encrypted=encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        ),
    )

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response(Protocol.OPENAI, route.upstream_model))

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    billing = FakeBilling()
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([route]),
    )
    path, body = _request(Protocol.OPENAI, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={
            "authorization": f"Bearer {RAW_KEY}",
            "idempotency-key": "shared-client-key",
            "x-request-id": "shared-request-id",
        },
    ) as client:
        first = await client.post(path, json=body)
        second = await client.post(path, json=body)
    await upstream_client.aclose()

    assert first.status_code == second.status_code == 200
    assert len(set(billing.reservation_keys)) == 2
    assert all("shared-client-key" not in key for key in billing.reservation_keys)
    assert all("shared-request-id" not in key for key in billing.reservation_keys)


@pytest.mark.parametrize("network_error", [httpx.ReadError, httpx.WriteError, httpx.CloseError])
async def test_network_error_family_retries_distinct_route_and_audits_attempt(
    session: AsyncSession,
    network_error: type[httpx.NetworkError],
) -> None:
    settings = _settings()
    model = await _catalog(session)

    def route(route_id: int, native_model: str) -> RouteCandidate:
        return RouteCandidate(
            route_id=route_id,
            model_id=model.id,
            provider_id=route_id + 100,
            provider_protocol_id=route_id + 200,
            protocol=Protocol.OPENAI,
            base_url=f"https://provider-{route_id}.example",
            websocket_url=None,
            upstream_model=native_model,
            weight=100,
            provider_credential_encrypted=encrypt_secret(
                orjson.dumps({"api_key": "provider-secret"}).decode(),
                settings=settings,
            ),
        )

    routes = [route(101, "first-native"), route(102, "second-native")]
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(orjson.loads(request.content)["model"])
        if len(seen) == 1:
            raise network_error("network failed", request=request)
        return httpx.Response(200, json=_response(Protocol.OPENAI, "second-native"))

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    router = FakeRouter(routes)
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    path, body = _request(Protocol.OPENAI, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200
    assert seen == ["first-native", "second-native"]
    assert router.failures == [101]
    assert router.successes == [102]
    assert audit.completed is not None
    assert [item["route_id"] for item in audit.completed.metadata["attempts"]] == [101, 102]


async def test_network_failover_is_bounded_by_distinct_routes(session: AsyncSession) -> None:
    settings = _settings()
    model = await _catalog(session)
    encrypted = encrypt_secret(
        orjson.dumps({"api_key": "provider-secret"}).decode(),
        settings=settings,
    )
    routes = [
        RouteCandidate(
            route_id=route_id,
            model_id=model.id,
            provider_id=route_id + 100,
            provider_protocol_id=route_id + 200,
            protocol=Protocol.OPENAI,
            base_url=f"https://provider-{route_id}.example",
            websocket_url=None,
            upstream_model=f"native-{route_id}",
            weight=100,
            provider_credential_encrypted=encrypted,
        )
        for route_id in (111, 112)
    ]
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadError("network failed", request=request)

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter(routes),
    )
    path, body = _request(Protocol.OPENAI, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 502
    assert calls == 2
    assert audit.failed is not None
    assert [item["route_id"] for item in audit.failed.metadata["attempts"]] == [111, 112]


async def test_cross_protocol_invalid_response_penalizes_route_and_fails_over(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    encrypted = encrypt_secret(
        orjson.dumps({"api_key": "provider-secret"}).decode(),
        settings=settings,
    )
    routes = [
        RouteCandidate(
            route_id=route_id,
            model_id=model.id,
            provider_id=route_id + 100,
            provider_protocol_id=route_id + 200,
            protocol=protocol,
            base_url=f"https://provider-{route_id}.example",
            websocket_url=None,
            upstream_model=native_model,
            weight=100,
            provider_credential_encrypted=encrypted,
        )
        for route_id, protocol, native_model in (
            (113, Protocol.CLAUDE, "invalid-claude"),
            (114, Protocol.OPENAI, "valid-openai"),
        )
    ]
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={"secret": "malformed-provider-response"},
            )
        return httpx.Response(200, json=_response(Protocol.OPENAI, "valid-openai"))

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    router = FakeRouter(routes)
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    path, body = _request(Protocol.GEMINI, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200, response.text
    assert get_adapter(Protocol.GEMINI).decode_response(response.json()).model == "valid-openai"
    assert calls == 2
    assert router.failures == [113]
    assert router.successes == [114]
    assert audit.completed is not None
    attempts = audit.completed.metadata["attempts"]
    assert [item["route_id"] for item in attempts] == [113, 114]
    assert attempts[0]["outcome"] == "failure"
    assert attempts[0]["error_code"] == "invalid_response"
    assert "malformed-provider-response" not in str(attempts)


async def test_final_cross_protocol_invalid_response_is_audited_without_health_success(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    route = RouteCandidate(
        route_id=115,
        model_id=model.id,
        provider_id=215,
        provider_protocol_id=315,
        protocol=Protocol.CLAUDE,
        base_url="https://provider.example",
        websocket_url=None,
        upstream_model="invalid-claude",
        weight=100,
        provider_credential_encrypted=encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        ),
    )
    malformed_body = orjson.dumps({"secret": "malformed-provider-response"})

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=malformed_body,
            headers={"content-type": "application/json"},
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    router = FakeRouter([route])
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    path, body = _request(Protocol.GEMINI, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 502
    assert "malformed-provider-response" not in response.text
    assert router.failures == [115]
    assert router.successes == []
    assert audit.failed is not None
    assert audit.failed.body == malformed_body
    assert audit.failed.headers["content-type"] == "application/json"
    attempts = audit.failed.metadata["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "failure"
    assert attempts[0]["error_code"] == "invalid_response"
    assert "malformed-provider-response" not in str(attempts)


async def test_cross_protocol_upstream_400_is_not_retried_and_uses_native_error(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    route = RouteCandidate(
        route_id=121,
        model_id=model.id,
        provider_id=122,
        provider_protocol_id=123,
        protocol=Protocol.OPENAI,
        base_url="https://provider.example",
        websocket_url=None,
        upstream_model="native-openai-error",
        weight=100,
        provider_credential_encrypted=encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        ),
    )
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([route]),
    )
    path, body = _request(Protocol.CLAUDE, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert calls == 1
    assert response.status_code == 502
    assert response.json()["error"]["type"] == "upstream_error"


def test_internal_billing_key_is_namespaced_by_user_and_api_key() -> None:
    request_id = uuid4()
    first = _billing_key(
        ApiKeyPrincipal(api_key_id=10, user_id=20, scope=ApiKeyScope.ALL),
        request_id,
    )
    second = _billing_key(
        ApiKeyPrincipal(api_key_id=11, user_id=21, scope=ApiKeyScope.ALL),
        request_id,
    )

    assert first != second
    assert first == f"gateway:20:10:{request_id}"
    assert second == f"gateway:21:11:{request_id}"


async def test_cleanup_failures_do_not_replace_original_cancellation(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    original = asyncio.CancelledError("client disconnected")

    class CancellingRouter(FakeRouter):
        async def select_route(self, *_: Any, **__: Any) -> RouteCandidate:
            raise original

    class FailingBilling(FakeBilling):
        async def settle_request(self, **_: Any) -> SettlementResult:
            raise RuntimeError("cleanup settlement failed")

    class FailingAudit(FakeAudit):
        async def fail_request(self, _: UUID, __: RequestFailure) -> None:
            raise RuntimeError("cleanup audit failed")

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None))
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FailingBilling(),  # type: ignore[arg-type]
        audit_service=FailingAudit(),  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: CancellingRouter([]),
    )
    path, body = _request(Protocol.OPENAI, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        with pytest.raises(asyncio.CancelledError) as caught:
            await client.post(path, json=body)
    await upstream_client.aclose()

    assert caught.value is original


async def test_nonstream_completed_usage_is_recoverable_when_settlement_fails(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    alias = model.aliases[0].alias
    upstream_model = "native-recovery"
    route = RouteCandidate(
        route_id=121,
        model_id=model.id,
        provider_id=221,
        provider_protocol_id=321,
        protocol=Protocol.OPENAI,
        base_url="https://provider.example/v1",
        websocket_url=None,
        upstream_model=upstream_model,
        weight=100,
        provider_credential_encrypted=encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        ),
    )

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response(Protocol.OPENAI, upstream_model))

    class FailingSettlementBilling(FakeBilling):
        async def settle_request(self, **_: Any) -> SettlementResult:
            self.settlements += 1
            raise RuntimeError("database unavailable")

    billing = FailingSettlementBilling()
    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([route]),
    )
    path, body = _request(Protocol.OPENAI, alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service), raise_app_exceptions=False),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 500
    assert billing.reservation_recoveries[0].cost == Decimal("0")
    assert billing.recovery_updates[-1].usage.input_tokens == 3
    assert billing.recovery_updates[-1].usage.output_tokens == 2
    assert billing.recovery_updates[-1].cost == Decimal("0.00000070")
    assert billing.settlements == 2


@pytest.mark.parametrize("failure_kind", ["network", "status"])
async def test_health_failure_write_is_auxiliary_to_bounded_failover(
    session: AsyncSession,
    failure_kind: str,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    encrypted = encrypt_secret(
        orjson.dumps({"api_key": "provider-secret"}).decode(),
        settings=settings,
    )
    routes = [
        RouteCandidate(
            route_id=route_id,
            model_id=model.id,
            provider_id=route_id + 100,
            provider_protocol_id=route_id + 200,
            protocol=Protocol.OPENAI,
            base_url=f"https://provider-{route_id}.example",
            websocket_url=None,
            upstream_model=f"native-{route_id}",
            weight=100,
            provider_credential_encrypted=encrypted,
        )
        for route_id in (131, 132)
    ]

    class FailingHealthRouter(FakeRouter):
        async def record_failure(self, route_id: int, _: object) -> bool:
            self.failures.append(route_id)
            raise RuntimeError("health-secret-must-not-leak")

    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            if failure_kind == "network":
                raise httpx.ReadError("network-secret-must-not-leak", request=request)
            return httpx.Response(503, json={"secret": "status-secret-must-not-leak"})
        return httpx.Response(200, json=_response(Protocol.OPENAI, "native-132"))

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    router = FailingHealthRouter(routes)
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    path, body = _request(Protocol.OPENAI, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200
    assert calls == 2
    assert router.failures == [131]
    assert audit.completed is not None
    assert [item["route_id"] for item in audit.completed.metadata["attempts"]] == [131, 132]
    audit_text = str(audit.completed.metadata)
    assert "secret" not in audit_text
    assert "provider-secret" not in audit_text


async def test_health_success_write_is_auxiliary_to_successful_response(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    route = RouteCandidate(
        route_id=141,
        model_id=model.id,
        provider_id=142,
        provider_protocol_id=143,
        protocol=Protocol.OPENAI,
        base_url="https://provider.example",
        websocket_url=None,
        upstream_model="native-health-success",
        weight=100,
        provider_credential_encrypted=encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        ),
    )

    class FailingSuccessRouter(FakeRouter):
        async def record_success(self, route_id: int) -> bool:
            self.successes.append(route_id)
            raise RuntimeError("success-health-secret")

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_response(Protocol.OPENAI, route.upstream_model))

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    router = FailingSuccessRouter([route])
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    path, body = _request(Protocol.OPENAI, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200
    assert router.successes == [141]
    assert audit.completed is not None
    assert audit.completed.model_route_id == 141
    assert "secret" not in str(audit.completed.metadata)


async def test_retry_response_close_failure_is_auxiliary_to_failover(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    encrypted = encrypt_secret(
        orjson.dumps({"api_key": "provider-secret"}).decode(),
        settings=settings,
    )
    routes = [
        RouteCandidate(
            route_id=route_id,
            model_id=model.id,
            provider_id=route_id + 100,
            provider_protocol_id=route_id + 200,
            protocol=Protocol.OPENAI,
            base_url=f"https://provider-{route_id}.example",
            websocket_url=None,
            upstream_model=f"native-{route_id}",
            weight=100,
            provider_credential_encrypted=encrypted,
        )
        for route_id in (151, 152)
    ]
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            response = httpx.Response(503, json={"error": "temporary"})

            async def failing_close() -> None:
                raise RuntimeError("close-secret-must-not-leak")

            response.aclose = failing_close  # type: ignore[method-assign]
            return response
        return httpx.Response(200, json=_response(Protocol.OPENAI, "native-152"))

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter(routes),
    )
    path, body = _request(Protocol.OPENAI, model.aliases[0].alias)
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200
    assert calls == 2
    assert audit.completed is not None
    assert [item["route_id"] for item in audit.completed.metadata["attempts"]] == [151, 152]
    assert "secret" not in str(audit.completed.metadata)
    assert (
        upstream_url(Protocol.CLAUDE, "https://provider.example", "native-model")
        == "https://provider.example/v1/messages"
    )
    assert (
        upstream_url(Protocol.GEMINI, "https://provider.example", "native/model")
        == "https://provider.example/v1beta/models/native%2Fmodel:generateContent"
    )


def test_model_not_found_retains_stable_gateway_code() -> None:
    assert ModelNotFound("missing").code == "model_not_found"


@pytest.mark.parametrize("protocol", list(Protocol))
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (
            HTTPException(
                401,
                detail={"code": "invalid_api_key", "message": "Invalid API key"},
            ),
            401,
            "invalid_api_key",
        ),
        (ModelNotFound("missing"), 404, "model_not_found"),
        (NoRouteAvailable("missing"), 503, "no_route_available"),
        (
            InsufficientBalance(required=Decimal("1"), available=Decimal("0")),
            402,
            "insufficient_balance",
        ),
        (UnsupportedFeatureError("stream", "unsupported"), 422, "unsupported_feature"),
        (UpstreamError("failed"), 502, "upstream_error"),
        (UpstreamTimeout("timed out"), 504, "upstream_timeout"),
    ],
)
def test_gateway_errors_use_native_protocol_envelopes(
    protocol: Protocol,
    error: BaseException,
    expected_status: int,
    expected_code: str,
) -> None:
    response = native_error_response(protocol, error)
    payload = orjson.loads(response.body)

    assert response.status_code == expected_status
    if protocol is Protocol.OPENAI:
        assert payload["error"]["code"] == expected_code
    elif protocol is Protocol.CLAUDE:
        assert payload["type"] == "error"
        assert payload["error"]["type"] == expected_code
        assert payload["error"]["message"]
    else:
        assert payload["error"]["code"] == expected_status
        assert isinstance(payload["error"]["status"], str)
