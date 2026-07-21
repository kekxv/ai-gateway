from __future__ import annotations

from dataclasses import dataclass
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
from ai_gateway.billing.service import BalanceReservation, InsufficientBalance, SettlementResult
from ai_gateway.catalog.repository import ModelNotFound
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import ApiKeyScope, Protocol
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

    async def reserve_balance(self, **_: Any) -> BalanceReservation:
        return self.reservation

    async def settle_request(self, **kwargs: Any) -> SettlementResult:
        self.settlements += 1
        return SettlementResult(
            account_id=1,
            request_id="request",
            reserved_amount=Decimal("1"),
            actual_cost=kwargs.get("cost", Decimal("0")),
            charged_amount=kwargs.get("cost", Decimal("0")),
            balance=Decimal("9"),
            total_spent=kwargs.get("cost", Decimal("0")),
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


class FakeRouter:
    def __init__(self, routes: list[RouteCandidate]) -> None:
        self.routes = routes
        self.successes: list[int] = []
        self.failures: list[int] = []

    async def select_route(
        self,
        _: int,
        __: Any,
        required_protocol: Protocol | str | None = None,
        *,
        requested_model: str | None = None,
        excluded_route_ids: frozenset[int] | set[int] = frozenset(),
    ) -> RouteCandidate:
        del required_protocol, requested_model
        for route in self.routes:
            if route.route_id not in excluded_route_ids:
                return route
        raise NoRouteAvailable("gateway-alias")

    async def record_success(self, route_id: int) -> bool:
        self.successes.append(route_id)
        return True

    async def record_failure(self, route_id: int, _: object) -> bool:
        self.failures.append(route_id)
        return True


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
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
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
            "usage": {"input_tokens": 3, "output_tokens": 2},
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
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2},
    }


def _app(service: GatewayService) -> FastAPI:
    app = FastAPI()
    app.include_router(openai_router)
    app.include_router(claude_router)
    app.include_router(gemini_router)
    app.dependency_overrides[get_gateway_service] = lambda: service
    return app


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
    assert upstream_payload["model"] == upstream_model
    assert alias not in seen[0].content.decode()
    assert model.canonical_name not in seen[0].content.decode()
    get_adapter(outbound).decode_request(upstream_payload)
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
    assert billing.settlements == 1


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
    assert upstream_payload["model"] == upstream_model
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


def test_upstream_urls_use_native_generation_endpoints_and_route_model() -> None:
    assert (
        upstream_url(Protocol.OPENAI, "https://provider.example/v1", "native-model")
        == "https://provider.example/v1/chat/completions"
    )
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
