from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import orjson
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ai_gateway.audit.service import RequestContext, RequestFailure, RequestResult
from ai_gateway.auth.api_key import ApiKeyPrincipal
from ai_gateway.billing.service import BalanceReservation, SettlementResult
from ai_gateway.catalog.schemas import ResolvedModel
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import ApiKeyScope, Protocol
from ai_gateway.core.security import encrypt_secret
from ai_gateway.db.models import Model, Provider
from ai_gateway.gateway import service as service_module
from ai_gateway.gateway.dependencies import get_gateway_service
from ai_gateway.gateway.openai import router as openai_router
from ai_gateway.gateway.service import (
    GatewayService,
    _convert_response,
    _outbound_openai_operation,
    _PreparedRequest,
    _upstream_body,
    upstream_url,
)
from ai_gateway.protocols.base import decode_sse
from ai_gateway.protocols.openai import OpenAIAdapter
from ai_gateway.protocols.types import CanonicalUsage
from ai_gateway.routing.types import NoRouteAvailable, RouteCandidate


@dataclass
class BillingRecorder:
    settled_usage: CanonicalUsage | None = None

    async def reserve_balance(self, **_: Any) -> BalanceReservation:
        return BalanceReservation(
            ledger_entry_id=1,
            account_id=1,
            user_id=1,
            request_id="request",
            idempotency_key="key",
            amount=Decimal("1"),
            balance_after=Decimal("9"),
        )

    async def update_reservation_recovery(self, **_: Any) -> bool:
        return True

    async def settle_request(self, **kwargs: Any) -> SettlementResult:
        self.settled_usage = kwargs.get("usage", self.settled_usage)
        return SettlementResult(
            account_id=1,
            request_id="request",
            reserved_amount=Decimal("1"),
            actual_cost=Decimal("0"),
            charged_amount=Decimal("0"),
            balance=Decimal("9"),
            total_spent=Decimal("0"),
            exhausted=False,
        )


class NullAudit:
    async def start_request(
        self,
        _: RequestContext,
        __: bytes,
        *,
        request_id: UUID | None = None,
    ) -> UUID:
        return request_id or uuid4()

    async def complete_request(self, _: UUID, __: RequestResult) -> None:
        return None

    async def fail_request(self, _: UUID, __: RequestFailure) -> None:
        return None


@dataclass
class RouteRecorder:
    route: RouteCandidate
    required_protocols: list[Protocol | str | None] = field(default_factory=list)

    async def select_route(
        self,
        _: int,
        __: ApiKeyPrincipal,
        required_protocol: Protocol | str | None = None,
        *,
        requested_model: str | None = None,
        excluded_route_ids: frozenset[int] | set[int] = frozenset(),
    ) -> RouteCandidate:
        del requested_model
        self.required_protocols.append(required_protocol)
        if self.route.route_id in excluded_route_ids:
            raise NoRouteAvailable("alias")
        return self.route

    async def record_success(self, _: int) -> bool:
        return True

    async def record_failure(self, _: int, __: object) -> bool:
        return True


class HttpClients:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def client_for(self, _: str | httpx.URL) -> httpx.AsyncClient:
        return self.client


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks: Iterable[bytes]) -> None:
        self.chunks = tuple(chunks)

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk


class FakeSession:
    def __init__(self, model: Model, provider: Provider) -> None:
        self.model = model
        self.provider = provider

    async def get(self, entity: type[object], _: int) -> object | None:
        if entity is Model:
            return self.model
        if entity is Provider:
            return self.provider
        return None


class FakeCatalog:
    resolved: ResolvedModel

    def __init__(self, _: object) -> None:
        pass

    async def resolve_model(self, _: str) -> ResolvedModel:
        return self.resolved


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret="gateway-contract-jwt-secret",
        encryption_key=Fernet.generate_key().decode(),
    )


def _sse_frame(payload: dict[str, object]) -> bytes:
    return b"data: " + orjson.dumps(payload) + b"\n\n"


def _gateway_for_route(
    monkeypatch: pytest.MonkeyPatch,
    *,
    settings: Settings,
    route: RouteCandidate,
    upstream_client: httpx.AsyncClient,
) -> tuple[FastAPI, BillingRecorder, RouteRecorder]:
    model = Model(
        id=1,
        canonical_name="canonical",
        display_name="Canonical",
        input_price_per_million=Decimal("0.1"),
        output_price_per_million=Decimal("0.2"),
    )
    provider = Provider(
        id=2,
        name="provider",
        credential_encrypted=b"unused",
        price_multiplier=Decimal("1"),
    )
    FakeCatalog.resolved = ResolvedModel(1, "alias", "canonical")

    async def authenticate(_: str, __: object) -> ApiKeyPrincipal:
        return ApiKeyPrincipal(api_key_id=3, user_id=4, scope=ApiKeyScope.ALL)

    monkeypatch.setattr(service_module, "authenticate_api_key", authenticate)
    monkeypatch.setattr(service_module, "CatalogRepository", FakeCatalog)

    router = RouteRecorder(route)
    billing = BillingRecorder()
    service = GatewayService(
        session=FakeSession(model, provider),  # type: ignore[arg-type]
        settings=settings,
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=NullAudit(),  # type: ignore[arg-type]
        http_client_factory=HttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    app = FastAPI()
    app.include_router(openai_router)
    app.dependency_overrides[get_gateway_service] = lambda: service
    return app, billing, router


@pytest.mark.parametrize(
    ("path", "payload", "upstream_body", "expected_suffix", "required_protocol", "usage"),
    [
        (
            "/v1/responses",
            {
                "model": "alias",
                "instructions": "Be concise.",
                "input": "hello",
                "max_output_tokens": 32,
                "store": False,
                "previous_response_id": "resp_previous",
                "tools": [{"type": "web_search"}],
            },
            {
                "id": "resp_native",
                "object": "response",
                "status": "completed",
                "model": "upstream-model",
                "output": [],
                "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
            },
            "/v1/responses",
            None,
            CanonicalUsage(11, 7),
        ),
        (
            "/v1/embeddings",
            {"model": "alias", "input": ["hello"], "encoding_format": "float"},
            {
                "object": "list",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
                "model": "upstream-model",
                "usage": {"prompt_tokens": 9, "total_tokens": 9},
            },
            "/v1/embeddings",
            Protocol.OPENAI,
            CanonicalUsage(9, 0),
        ),
        (
            "/v1/completions",
            {"model": "alias", "prompt": "hello", "max_tokens": 12, "echo": True},
            {
                "id": "cmpl_native",
                "object": "text_completion",
                "model": "upstream-model",
                "choices": [{"index": 0, "text": "hello world", "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            },
            "/v1/completions",
            Protocol.OPENAI,
            CanonicalUsage(4, 2),
        ),
    ],
)
async def test_openai_native_operations_use_matching_upstream_endpoint_and_preserve_response(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: dict[str, Any],
    upstream_body: dict[str, Any],
    expected_suffix: str,
    required_protocol: Protocol | None,
    usage: CanonicalUsage,
) -> None:
    settings = _settings()
    model = Model(
        id=1,
        canonical_name="canonical",
        display_name="Canonical",
        input_price_per_million=Decimal("0.1"),
        output_price_per_million=Decimal("0.2"),
    )
    provider = Provider(
        id=2,
        name="provider",
        credential_encrypted=b"unused",
        price_multiplier=Decimal("1"),
    )
    FakeCatalog.resolved = ResolvedModel(1, "alias", "canonical")

    async def authenticate(_: str, __: object) -> ApiKeyPrincipal:
        return ApiKeyPrincipal(api_key_id=3, user_id=4, scope=ApiKeyScope.ALL)

    monkeypatch.setattr(service_module, "authenticate_api_key", authenticate)
    monkeypatch.setattr(service_module, "CatalogRepository", FakeCatalog)

    route = RouteCandidate(
        route_id=5,
        model_id=1,
        provider_id=2,
        provider_protocol_id=6,
        protocol=Protocol.OPENAI,
        base_url="https://upstream.example/v1",
        websocket_url=None,
        upstream_model="upstream-model",
        weight=100,
        supports_responses=True,
        provider_credential_encrypted=encrypt_secret("{}", settings=settings),
    )
    router = RouteRecorder(route)
    seen: list[httpx.Request] = []
    raw_response = b"{\n  " + orjson.dumps(upstream_body)[1:-1] + b"\n}"

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=raw_response,
            headers={"content-type": "application/json"},
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    billing = BillingRecorder()
    service = GatewayService(
        session=FakeSession(model, provider),  # type: ignore[arg-type]
        settings=settings,
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=NullAudit(),  # type: ignore[arg-type]
        http_client_factory=HttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    app = FastAPI()
    app.include_router(openai_router)
    app.dependency_overrides[get_gateway_service] = lambda: service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://gateway.test",
        headers={"authorization": "Bearer sk-gw-test"},
    ) as client:
        response = await client.post(path, json=payload)
    await upstream_client.aclose()

    assert response.status_code == 200, response.text
    assert len(seen) == 1
    assert seen[0].url.path.endswith(expected_suffix)
    forwarded = orjson.loads(seen[0].content)
    assert forwarded == {**payload, "model": "upstream-model"}
    assert response.content == raw_response
    assert router.required_protocols == [required_protocol]
    assert billing.settled_usage == usage


@pytest.mark.parametrize(
    ("operation", "suffix"),
    [
        ("chat_completions", "/v1/chat/completions"),
        ("responses", "/v1/responses"),
        ("embeddings", "/v1/embeddings"),
        ("completions", "/v1/completions"),
    ],
)
def test_openai_upstream_url_is_operation_aware(operation: str, suffix: str) -> None:
    assert upstream_url(
        Protocol.OPENAI,
        "https://upstream.example/v1",
        "model",
        openai_operation=operation,
    ).endswith(suffix)


def test_responses_falls_back_to_chat_only_when_route_explicitly_disables_support() -> None:
    payload = {
        "model": "alias",
        "instructions": "Be concise.",
        "input": [{"type": "message", "role": "user", "content": "hello"}],
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "description": "Look up a record",
                "parameters": {"type": "object", "properties": {}},
                "strict": True,
            }
        ],
        "tool_choice": {"type": "function", "name": "lookup"},
        "max_output_tokens": 32,
    }
    canonical = OpenAIAdapter().decode_responses_request(payload)
    prepared = _PreparedRequest(
        raw_body=orjson.dumps(payload),
        payload=payload,
        canonical=canonical,
        requested_model="alias",
        inbound_protocol=Protocol.OPENAI,
        endpoint_path="/v1/responses",
        openai_operation="responses",
    )
    route = RouteCandidate(
        route_id=9,
        model_id=1,
        provider_id=2,
        provider_protocol_id=3,
        protocol=Protocol.OPENAI,
        base_url="https://legacy.example/v1",
        websocket_url=None,
        upstream_model="upstream-model",
        weight=100,
        supports_responses=False,
    )

    assert _outbound_openai_operation(prepared, route) == "chat_completions"
    forwarded = orjson.loads(_upstream_body(prepared, route))
    assert forwarded["model"] == "upstream-model"
    assert forwarded["messages"] == [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "hello"},
    ]
    assert forwarded["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Look up a record",
                "parameters": {"type": "object", "properties": {}},
                "strict": True,
            },
        }
    ]
    assert forwarded["tool_choice"] == {
        "type": "function",
        "function": {"name": "lookup"},
    }
    assert forwarded["max_completion_tokens"] == 32

    upstream = httpx.Response(
        200,
        json={
            "id": "chatcmpl_123",
            "object": "chat.completion",
            "model": "upstream-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "done"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        },
    )
    output, _, _ = _convert_response(
        inbound_protocol=Protocol.OPENAI,
        endpoint_path="/v1/responses",
        openai_operation="responses",
        route=route,
        upstream=upstream,
    )
    response = orjson.loads(output.body)
    assert response["object"] == "response"
    assert response["status"] == "completed"
    assert response["output"][0]["content"][0]["text"] == "done"
    assert response["usage"]["input_tokens"] == 3
    assert response["usage"]["output_tokens"] == 1


def test_openai_to_claude_uses_gateway_default_when_output_limit_is_omitted() -> None:
    payload = {
        "model": "alias",
        "messages": [{"role": "user", "content": "hello"}],
    }
    prepared = _PreparedRequest(
        raw_body=orjson.dumps(payload),
        payload=payload,
        canonical=OpenAIAdapter().decode_request(payload),
        requested_model="alias",
        inbound_protocol=Protocol.OPENAI,
    )
    route = RouteCandidate(
        route_id=12,
        model_id=1,
        provider_id=2,
        provider_protocol_id=3,
        protocol=Protocol.CLAUDE,
        base_url="https://claude.example/v1",
        websocket_url=None,
        upstream_model="upstream-model",
        weight=100,
        supports_responses=True,
    )

    forwarded = orjson.loads(
        _upstream_body(prepared, route, default_max_output_tokens=2048)
    )

    assert forwarded["max_tokens"] == 2048


async def test_native_responses_stream_is_forwarded_byte_for_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    route = RouteCandidate(
        route_id=10,
        model_id=1,
        provider_id=2,
        provider_protocol_id=3,
        protocol=Protocol.OPENAI,
        base_url="https://responses.example/v1",
        websocket_url=None,
        upstream_model="upstream-model",
        weight=100,
        supports_responses=True,
        provider_credential_encrypted=encrypt_secret("{}", settings=settings),
    )
    frames = (
        b"id: vendor-created\nevent: response.created\ndata: "
        + orjson.dumps(
            {
                "type": "response.created",
                "sequence_number": 0,
                "response": {"id": "resp_native", "status": "in_progress"},
            }
        )
        + b"\n\n",
        b": vendor-heartbeat\n\n",
        b"event: response.output_text.delta\ndata: "
        + orjson.dumps(
            {
                "type": "response.output_text.delta",
                "sequence_number": 1,
                "response_id": "resp_native",
                "item_id": "msg_native",
                "output_index": 0,
                "content_index": 0,
                "delta": "Hello",
                "vendor_extension": {"preserve": True},
            }
        )
        + b"\n\n",
        b"event: response.completed\ndata: "
        + orjson.dumps(
            {
                "type": "response.completed",
                "sequence_number": 2,
                "response": {
                    "id": "resp_native",
                    "status": "completed",
                    "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
                },
            }
        )
        + b"\n\n",
    )
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            stream=ChunkStream(frames),
            headers={"content-type": "text/event-stream"},
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app, billing, router = _gateway_for_route(
        monkeypatch,
        settings=settings,
        route=route,
        upstream_client=upstream_client,
    )
    payload = {
        "model": "alias",
        "input": "hello",
        "stream": True,
        "previous_response_id": "resp_previous",
        "tools": [{"type": "web_search"}],
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://gateway.test",
        headers={"authorization": "Bearer sk-gw-test"},
    ) as client:
        response = await client.post("/v1/responses", json=payload)
    await upstream_client.aclose()

    assert response.status_code == 200, response.text
    assert response.content == b"".join(frames)
    assert seen[0].url.path == "/v1/responses"
    assert orjson.loads(seen[0].content) == {**payload, "model": "upstream-model"}
    assert router.required_protocols == [None]
    assert billing.settled_usage == CanonicalUsage(5, 2)


async def test_responses_chat_fallback_stream_uses_official_event_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    route = RouteCandidate(
        route_id=11,
        model_id=1,
        provider_id=2,
        provider_protocol_id=3,
        protocol=Protocol.OPENAI,
        base_url="https://chat-only.example/v1",
        websocket_url=None,
        upstream_model="upstream-model",
        weight=100,
        supports_responses=False,
        provider_credential_encrypted=encrypt_secret("{}", settings=settings),
    )
    chat_frames = (
        _sse_frame(
            {
                "model": "upstream-model",
                "choices": [{"index": 0, "delta": {"role": "assistant"}}],
            }
        ),
        _sse_frame(
            {
                "model": "upstream-model",
                "choices": [{"index": 0, "delta": {"content": "Hello"}}],
            }
        ),
        _sse_frame(
            {
                "model": "upstream-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        ),
        _sse_frame(
            {
                "model": "upstream-model",
                "choices": [],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 1,
                    "total_tokens": 5,
                },
            }
        ),
        b"data: [DONE]\n\n",
    )
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            stream=ChunkStream(chat_frames),
            headers={"content-type": "text/event-stream"},
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app, billing, _ = _gateway_for_route(
        monkeypatch,
        settings=settings,
        route=route,
        upstream_client=upstream_client,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://gateway.test",
        headers={"authorization": "Bearer sk-gw-test"},
    ) as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "alias", "input": "hello", "stream": True},
        )
    await upstream_client.aclose()

    assert response.status_code == 200, response.text
    assert seen[0].url.path == "/v1/chat/completions"
    forwarded = orjson.loads(seen[0].content)
    assert forwarded["messages"] == [{"role": "user", "content": "hello"}]
    assert forwarded["stream"] is True
    assert forwarded["stream_options"] == {"include_usage": True}

    frames = [frame + b"\n\n" for frame in response.content.split(b"\n\n") if frame]
    decoded = [decode_sse(frame) for frame in frames]
    payloads = [payload for _, payload in decoded]
    assert [event_name for event_name, _ in decoded] == [payload["type"] for payload in payloads]
    assert [payload["sequence_number"] for payload in payloads] == list(range(len(payloads)))
    assert any(
        payload["type"] == "response.output_text.delta" and payload["delta"] == "Hello"
        for payload in payloads
    )
    completed = payloads[-1]
    assert completed["type"] == "response.completed"
    assert completed["response"]["status"] == "completed"
    assert completed["response"]["output"][0]["content"][0]["text"] == "Hello"
    assert completed["response"]["usage"]["total_tokens"] == 5
    assert billing.settled_usage == CanonicalUsage(4, 1)


async def test_responses_fallback_rejects_nonportable_fields_before_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    route = RouteCandidate(
        route_id=13,
        model_id=1,
        provider_id=2,
        provider_protocol_id=3,
        protocol=Protocol.OPENAI,
        base_url="https://chat-only.example/v1",
        websocket_url=None,
        upstream_model="upstream-model",
        weight=100,
        supports_responses=False,
        provider_credential_encrypted=encrypt_secret("{}", settings=settings),
    )
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(500)

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app, _, _ = _gateway_for_route(
        monkeypatch,
        settings=settings,
        route=route,
        upstream_client=upstream_client,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://gateway.test",
        headers={"authorization": "Bearer sk-gw-test"},
    ) as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "alias",
                "input": "hello",
                "previous_response_id": "resp_previous",
            },
        )
    await upstream_client.aclose()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_feature"
    assert "previous_response_id" in response.json()["error"]["message"]
    assert seen == []
