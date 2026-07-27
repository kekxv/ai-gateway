from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import httpx
import orjson
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.audit.service import RequestContext, RequestFailure, RequestResult
from ai_gateway.auth.api_key import ApiKeyPrincipal
from ai_gateway.billing.service import BalanceReservation, ReservationRecovery, SettlementResult
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import ApiKeyScope, Protocol
from ai_gateway.core.security import encrypt_secret
from ai_gateway.db.models import ApiKey, Model, ModelAlias, User
from ai_gateway.gateway.claude import router as claude_router
from ai_gateway.gateway.dependencies import get_gateway_service
from ai_gateway.gateway.gemini import router as gemini_router
from ai_gateway.gateway.openai import router as openai_router
from ai_gateway.gateway.service import GatewayService
from ai_gateway.protocols.base import decode_sse
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.protocols.types import CanonicalUsage, StreamEvent
from ai_gateway.routing.types import NoRouteAvailable, RouteCandidate
from ai_gateway.transport.sse import GatewayContext, SSEDecoder, SSEEvent, stream_gateway_response

RAW_KEY = "sk-gw-stream-key-123456789"


@dataclass
class FakeBilling:
    reservation: BalanceReservation = BalanceReservation(
        1,
        1,
        1,
        "request",
        "key",
        Decimal("1"),
        Decimal("9"),
    )
    settlements: int = 0
    reservation_recoveries: list[ReservationRecovery] = field(default_factory=list)
    recovery_updates: list[ReservationRecovery] = field(default_factory=list)

    async def reserve_balance(self, **kwargs: Any) -> BalanceReservation:
        self.reservation_recoveries.append(kwargs["recovery"])
        return self.reservation

    async def update_reservation_recovery(self, **kwargs: Any) -> bool:
        self.recovery_updates.append(kwargs["recovery"])
        return True

    async def settle_request(self, **kwargs: Any) -> SettlementResult:
        self.settlements += 1
        cost = kwargs.get("cost", Decimal("0"))
        return SettlementResult(1, "request", Decimal("1"), cost, cost, Decimal("9"), cost, False)


@dataclass
class FakeAudit:
    completed: RequestResult | None = None
    failed: RequestFailure | None = None

    async def start_request(
        self,
        _: RequestContext,
        __: bytes,
        *,
        request_id: UUID | None = None,
    ) -> UUID:
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

    async def select_route(
        self,
        _: int,
        __: ApiKeyPrincipal,
        required_protocol: Protocol | str | None = None,
        *,
        requested_model: str | None = None,
        excluded_route_ids: frozenset[int] | set[int] = frozenset(),
    ) -> RouteCandidate:
        del required_protocol, requested_model
        for route in self.routes:
            if route.route_id not in excluded_route_ids:
                return route
        raise NoRouteAvailable("stream-alias")

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
        jwt_secret="gateway-stream-jwt-secret",
        encryption_key=Fernet.generate_key().decode(),
    )


async def _catalog(session: AsyncSession) -> Model:
    user = User(email=f"stream-{uuid4()}@example.com", password_hash="unused")
    user.api_keys.append(
        ApiKey(
            name="stream",
            key_prefix=RAW_KEY[:12],
            key_hash=sha256(RAW_KEY.encode()).digest(),
            scope=ApiKeyScope.ALL,
        )
    )
    model = Model(
        canonical_name=f"canonical-{uuid4()}",
        display_name="Streaming Contract",
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
    return f"/v1beta/models/{model}:streamGenerateContent", {
        "contents": [{"role": "user", "parts": [{"text": "hello"}]}],
        "generationConfig": {"maxOutputTokens": 8},
    }


def _app(service: GatewayService) -> FastAPI:
    app = FastAPI()
    app.include_router(openai_router)
    app.include_router(claude_router)
    app.include_router(gemini_router)
    app.dependency_overrides[get_gateway_service] = lambda: service
    return app


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks: Iterable[bytes], *, fail_at: int | None = None) -> None:
        self.chunks = tuple(chunks)
        self.fail_at = fail_at
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index, chunk in enumerate(self.chunks):
            if index == self.fail_at:
                raise httpx.ReadError("failed during stream read")
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


def _sse(payload: dict[str, object], event: str | None = None) -> bytes:
    prefix = b"" if event is None else f"event: {event}\n".encode()
    return prefix + b"data: " + orjson.dumps(payload) + b"\n\n"


def _source_frames(protocol: Protocol) -> tuple[bytes, ...]:
    if protocol is Protocol.OPENAI:
        return (
            _sse({"model": "m", "choices": [{"index": 0, "delta": {"role": "assistant"}}]}),
            _sse({"model": "m", "choices": [{"index": 0, "delta": {"content": "Hi"}}]}),
            _sse(
                {
                    "model": "m",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "a",
                                        "type": "function",
                                        "function": {"name": "one", "arguments": '{"x":'},
                                    },
                                    {
                                        "index": 1,
                                        "id": "b",
                                        "type": "function",
                                        "function": {"name": "two", "arguments": '{"y":'},
                                    },
                                ]
                            },
                        }
                    ],
                }
            ),
            _sse(
                {
                    "model": "m",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {"index": 0, "function": {"arguments": "1}"}},
                                    {"index": 1, "function": {"arguments": "2}"}},
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                }
            ),
            _sse(
                {
                    "model": "m",
                    "choices": [],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3},
                }
            ),
            b"data: [DONE]\n\n",
        )
    if protocol is Protocol.CLAUDE:
        return (
            _sse(
                {
                    "type": "message_start",
                    "message": {"role": "assistant", "model": "m", "usage": {"input_tokens": 2}},
                },
                "message_start",
            ),
            _sse(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Hi"},
                },
                "content_block_delta",
            ),
            _sse(
                {
                    "type": "content_block_start",
                    "index": 1,
                    "content_block": {"type": "tool_use", "id": "a", "name": "one", "input": {}},
                },
                "content_block_start",
            ),
            _sse(
                {
                    "type": "content_block_delta",
                    "index": 1,
                    "delta": {"type": "input_json_delta", "partial_json": '{"x":1}'},
                },
                "content_block_delta",
            ),
            _sse({"type": "content_block_stop", "index": 1}, "content_block_stop"),
            _sse(
                {
                    "type": "content_block_start",
                    "index": 2,
                    "content_block": {"type": "tool_use", "id": "b", "name": "two", "input": {}},
                },
                "content_block_start",
            ),
            _sse(
                {
                    "type": "content_block_delta",
                    "index": 2,
                    "delta": {"type": "input_json_delta", "partial_json": '{"y":2}'},
                },
                "content_block_delta",
            ),
            _sse({"type": "content_block_stop", "index": 2}, "content_block_stop"),
            _sse(
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use"},
                    "usage": {"output_tokens": 3},
                },
                "message_delta",
            ),
            _sse({"type": "message_stop"}, "message_stop"),
        )
    return (
        _sse(
            {
                "modelVersion": "m",
                "candidates": [
                    {
                        "index": 0,
                        "content": {
                            "role": "model",
                            "parts": [
                                {"text": "Hi"},
                                {"functionCall": {"id": "a", "name": "one", "args": {"x": 1}}},
                                {"functionCall": {"id": "b", "name": "two", "args": {"y": 2}}},
                            ],
                        },
                    }
                ],
            }
        ),
        _sse(
            {
                "modelVersion": "m",
                "candidates": [{"index": 0, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 3},
            }
        ),
    )


def _odd_chunks(wire: bytes) -> tuple[bytes, ...]:
    cuts = (1, 3, 8, 13, 21, 34, 55)
    points = [point for point in cuts if point < len(wire)]
    return tuple(wire[start:end] for start, end in zip((0, *points), (*points, len(wire))))


def _decode_output(protocol: Protocol, wire: bytes) -> tuple[StreamEvent, ...]:
    parser = SSEDecoder()
    native = [*parser.feed(wire), *parser.finish()]
    decoder = get_adapter(protocol).create_stream_decoder()
    events = [event for frame in native for event in decoder.decode(frame.raw)]
    if protocol is Protocol.GEMINI:
        events.extend(decoder.decode(b""))
    return tuple(events)


@pytest.mark.parametrize("source", list(Protocol))
@pytest.mark.parametrize("target", list(Protocol))
async def test_all_nine_stream_pairs_convert_incrementally(
    source: Protocol,
    target: Protocol,
) -> None:
    upstream_wire = b"".join(_source_frames(source))
    stream = ChunkStream(_odd_chunks(upstream_wire))
    response = httpx.Response(200, stream=stream)
    context = GatewayContext(
        source_protocol=source,
        target_protocol=target,
        initial_input_tokens=2,
        audit_body_limit_bytes=256,
    )

    chunks = [chunk async for chunk in stream_gateway_response(context, response)]
    output = b"".join(chunks)

    if source is target:
        assert output == upstream_wire
    else:
        events = _decode_output(target, output)
        assert "".join(event.text or "" for event in events) == "Hi"
        tools: dict[int, str] = {}
        for event in events:
            if event.type == "tool_call_delta" and event.tool_index is not None:
                tools[event.tool_index] = tools.get(event.tool_index, "") + (
                    event.arguments_delta or ""
                )
        assert {
            orjson.loads(arguments)[next(iter(orjson.loads(arguments)))]
            for arguments in tools.values()
        } == {1, 2}
        assert (
            next(event for event in events if event.type == "message_end").finish_reason
            == "tool_call"
        )
        assert next(event for event in events if event.type == "usage").usage == CanonicalUsage(
            2, 3
        )

    assert context.observed_usage == CanonicalUsage(2, 3)
    assert context.first_token_ms is not None
    assert len(context.audit_preview) <= 256
    assert stream.closed


async def test_claude_target_places_input_usage_on_start_and_output_on_final_delta() -> None:
    source = Protocol.OPENAI
    upstream_wire = b"".join(_source_frames(source))
    response = httpx.Response(200, stream=ChunkStream(_odd_chunks(upstream_wire)))
    context = GatewayContext(source, Protocol.CLAUDE, initial_input_tokens=2)

    output = b"".join([chunk async for chunk in stream_gateway_response(context, response)])
    bodies = [decode_sse(event.raw)[1] for event in SSEDecoder().feed(output)]

    assert bodies[0]["type"] == "message_start"
    assert bodies[0]["message"]["usage"] == {"input_tokens": 2}
    terminal = next(body for body in bodies if body["type"] == "message_delta")
    assert terminal["delta"]["stop_reason"] == "tool_use"
    assert terminal["usage"] == {"output_tokens": 3}
    assert bodies[-1]["type"] == "message_stop"


async def test_gemini_eof_terminal_is_not_confused_with_encoder_no_output() -> None:
    upstream_wire = b"".join(_source_frames(Protocol.GEMINI))
    response = httpx.Response(200, stream=ChunkStream(_odd_chunks(upstream_wire)))
    context = GatewayContext(Protocol.GEMINI, Protocol.OPENAI, initial_input_tokens=2)

    output = b"".join([chunk async for chunk in stream_gateway_response(context, response)])

    assert output.count(b"data: [DONE]\n\n") == 1
    assert context.gemini_eof_decodes == 1


async def test_same_protocol_forwards_opaque_heartbeat_and_vendor_frames_exactly() -> None:
    heartbeat = b": provider-heartbeat\r\n\r\n"
    opaque = b"event: vendor_extension\r\ndata: not-json\r\n\r\n"
    terminal = b"data: [DONE]\n\n"
    stream = ChunkStream((heartbeat, opaque, terminal))
    response = httpx.Response(200, stream=stream)
    context = GatewayContext(Protocol.OPENAI, Protocol.OPENAI)
    body = stream_gateway_response(context, response)

    assert await anext(body) == heartbeat
    assert context.first_token_ms is None
    assert await anext(body) == opaque
    assert await anext(body) == terminal
    with pytest.raises(StopAsyncIteration):
        await anext(body)

    assert context.audit_preview == heartbeat + opaque + terminal
    assert stream.closed


async def test_openai_bom_is_normalized_only_for_cross_protocol_decoder() -> None:
    frames = _source_frames(Protocol.OPENAI)
    finish = _sse(
        {
            "model": "m",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    )
    native = b"\xef\xbb\xbf" + b"".join((frames[1], finish, frames[-1]))
    response = httpx.Response(200, stream=ChunkStream(_odd_chunks(native)))
    context = GatewayContext(Protocol.OPENAI, Protocol.GEMINI, initial_input_tokens=2)

    output = b"".join([chunk async for chunk in stream_gateway_response(context, response)])
    events = _decode_output(Protocol.GEMINI, output)

    assert "".join(event.text or "" for event in events) == "Hi"


async def test_openai_to_claude_estimates_terminal_usage_when_provider_omits_it() -> None:
    frames = _source_frames(Protocol.OPENAI)
    native = b"".join((*frames[:-2], frames[-1]))
    response = httpx.Response(200, stream=ChunkStream(_odd_chunks(native)))
    context = GatewayContext(Protocol.OPENAI, Protocol.CLAUDE, initial_input_tokens=2)

    output = b"".join([chunk async for chunk in stream_gateway_response(context, response)])
    bodies = [decode_sse(event.raw)[1] for event in SSEDecoder().feed(output)]

    terminal = next(body for body in bodies if body["type"] == "message_delta")
    assert terminal["delta"]["stop_reason"] == "tool_use"
    assert terminal["usage"]["output_tokens"] > 0
    assert bodies[-1]["type"] == "message_stop"


@pytest.mark.parametrize(
    ("source", "target", "terminal_frame"),
    (
        (Protocol.OPENAI, Protocol.CLAUDE, b"event: message_stop"),
        (Protocol.CLAUDE, Protocol.OPENAI, b"data: [DONE]"),
    ),
)
async def test_cross_protocol_eof_synthesizes_done_after_semantic_finish(
    source: Protocol,
    target: Protocol,
    terminal_frame: bytes,
) -> None:
    response = httpx.Response(200, stream=ChunkStream(_source_frames(source)[:-1]))
    context = GatewayContext(source, target, initial_input_tokens=2)

    output = b"".join([chunk async for chunk in stream_gateway_response(context, response)])
    events = _decode_output(target, output)

    assert output.count(terminal_frame) == 1
    assert (
        next(event for event in events if event.type == "message_end").finish_reason == "tool_call"
    )
    assert next(event for event in events if event.type == "usage").usage == CanonicalUsage(2, 3)
    assert sum(event.type == "done" for event in events) == 1


async def test_large_stream_retains_only_bounded_preview_and_incremental_count() -> None:
    frame = _sse({"model": "m", "choices": [{"index": 0, "delta": {"content": "abcdefgh"}}]})
    response = httpx.Response(
        200,
        stream=ChunkStream((*((frame,) * 10_000), b"data: [DONE]\n\n")),
    )
    context = GatewayContext(
        Protocol.OPENAI,
        Protocol.OPENAI,
        initial_input_tokens=2,
        audit_body_limit_bytes=64,
    )

    async for _ in stream_gateway_response(context, response):
        pass

    assert len(context.audit_preview) == 64
    assert context.estimated_output_tokens > 0
    assert not hasattr(context, "_response_content")


def test_output_estimate_is_fragmentation_independent_with_constant_state() -> None:
    text = "abcdefghij" * 1_000
    whole = GatewayContext(Protocol.OPENAI, Protocol.CLAUDE)
    fragmented = GatewayContext(Protocol.OPENAI, Protocol.CLAUDE)

    whole.observe(StreamEvent(type="content_delta", text=text))
    for character in text:
        fragmented.observe(StreamEvent(type="content_delta", text=character))

    assert whole.estimated_output_tokens == fragmented.estimated_output_tokens
    assert whole.estimated_output_tokens == (len(text.encode("utf-8")) + 3) // 4
    assert not hasattr(whole, "_response_content")
    assert not hasattr(fragmented, "_response_content")


def test_provider_usage_never_regresses_component_wise() -> None:
    context = GatewayContext(Protocol.OPENAI, Protocol.CLAUDE)

    context.observe(StreamEvent(type="usage", usage=CanonicalUsage(10, 5)))
    context.observe(StreamEvent(type="usage", usage=CanonicalUsage(8, 7)))
    context.observe(StreamEvent(type="usage", usage=CanonicalUsage(12, 6)))

    assert context.observed_usage == CanonicalUsage(12, 7)
    assert context.provider_usage_complete


def test_provider_cache_usage_never_regresses_component_wise() -> None:
    context = GatewayContext(Protocol.OPENAI, Protocol.CLAUDE)

    context.observe(StreamEvent(type="usage", usage=CanonicalUsage(10, 5, 7, 3)))
    context.observe(StreamEvent(type="usage", usage=CanonicalUsage(8, 7, 9, 2)))
    context.observe(StreamEvent(type="usage", usage=CanonicalUsage(12, 6, 8, 4)))

    assert context.observed_usage == CanonicalUsage(12, 7, 9, 4)
    assert context.estimated_usage() == CanonicalUsage(12, 0, 9, 4)


@pytest.mark.parametrize(
    ("protocol", "payload", "expected"),
    [
        (
            Protocol.OPENAI,
            {
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 7,
                    "prompt_tokens_details": {
                        "cached_tokens": 10,
                        "cache_write_tokens": 4,
                    },
                },
                "choices": [],
            },
            CanonicalUsage(86, 7, 10, 4),
        ),
        (
            Protocol.GEMINI,
            {
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 7,
                    "cachedContentTokenCount": 10,
                },
                "candidates": [],
            },
            CanonicalUsage(90, 7, 10),
        ),
    ],
)
def test_same_protocol_passthrough_observes_cache_usage(
    protocol: Protocol,
    payload: dict[str, object],
    expected: CanonicalUsage,
) -> None:
    context = GatewayContext(protocol, protocol)

    context.observe_passthrough(SSEEvent(data=orjson.dumps(payload), raw=b""))

    assert context.observed_usage == expected
    assert context.provider_usage_complete


def test_native_responses_passthrough_observes_cache_usage() -> None:
    context = GatewayContext(
        Protocol.OPENAI,
        Protocol.OPENAI,
        openai_operation="responses",
        native_openai_passthrough=True,
    )
    payload = {
        "type": "response.completed",
        "response": {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 7,
                "input_tokens_details": {
                    "cached_tokens": 10,
                    "cache_write_tokens": 4,
                },
            }
        },
    }

    context.observe_passthrough(SSEEvent(data=orjson.dumps(payload), raw=b""))

    assert context.observed_usage == CanonicalUsage(86, 7, 10, 4)
    assert context.provider_usage_complete


def test_claude_passthrough_combines_cache_input_with_final_output_usage() -> None:
    context = GatewayContext(Protocol.CLAUDE, Protocol.CLAUDE)
    start = {
        "type": "message_start",
        "message": {
            "usage": {
                "input_tokens": 6,
                "cache_read_input_tokens": 10,
                "cache_creation_input_tokens": 4,
            }
        },
    }
    end = {"type": "message_delta", "usage": {"output_tokens": 7}}

    context.observe_passthrough(SSEEvent(data=orjson.dumps(start), raw=b""))
    context.observe_passthrough(SSEEvent(data=orjson.dumps(end), raw=b""))

    assert context.observed_usage == CanonicalUsage(6, 7, 10, 4)
    assert context.provider_usage_complete


def _route(
    model_id: int,
    route_id: int,
    host: str,
    settings: object,
    protocol: Protocol = Protocol.OPENAI,
) -> object:
    from ai_gateway.routing.types import RouteCandidate

    return RouteCandidate(
        route_id=route_id,
        model_id=model_id,
        provider_id=route_id + 100,
        provider_protocol_id=route_id + 200,
        protocol=protocol,
        base_url=f"https://{host}.example/v1",
        websocket_url=None,
        upstream_model=f"native-{route_id}",
        weight=100,
        provider_credential_encrypted=encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,  # type: ignore[arg-type]
        ),
    )


async def test_first_read_network_error_fails_over_before_response_start(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    alias = model.aliases[0].alias
    routes = [
        _route(model.id, 71, "first-read-fails", settings),
        _route(model.id, 72, "second-read-works", settings),
    ]
    streams: list[ChunkStream] = []
    seen: list[str] = []
    seen_payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host or "")
        seen_payloads.append(orjson.loads(request.content))
        if request.url.host == "first-read-fails.example":
            stream = ChunkStream((), fail_at=0)
        else:
            stream = ChunkStream(_source_frames(Protocol.OPENAI))
        streams.append(stream)
        return httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    router = FakeRouter(routes)  # type: ignore[arg-type]
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    path, body = _request(Protocol.OPENAI, alias)
    body["stream"] = True
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200
    assert seen == ["first-read-fails.example", "second-read-works.example"]
    assert all("stream_options" not in payload for payload in seen_payloads)
    assert streams[0].closed and streams[1].closed
    assert router.failures == [71]
    assert router.successes == [72]
    assert audit.completed is not None
    assert [attempt["outcome"] for attempt in audit.completed.metadata["attempts"]] == [
        "failure",
        "success",
    ]


async def test_same_protocol_openai_preserves_explicit_include_usage_false(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    alias = model.aliases[0].alias
    route = _route(model.id, 73, "same-protocol-options", settings)
    seen_payload: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_payload.update(orjson.loads(request.content))
        return httpx.Response(200, stream=ChunkStream(_source_frames(Protocol.OPENAI)))

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([route]),  # type: ignore[list-item]
    )
    path, body = _request(Protocol.OPENAI, alias)
    body.update({"stream": True, "stream_options": {"include_usage": False}})
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200
    assert seen_payload["stream_options"] == {"include_usage": False}


async def test_malformed_first_sse_returns_native_error_before_200_start(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    alias = model.aliases[0].alias
    route = _route(model.id, 81, "malformed", settings)
    stream = ChunkStream((b"data: not-json\n\n",))

    seen_payload: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_payload.update(orjson.loads(request.content))
        return httpx.Response(200, stream=stream)

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    billing = FakeBilling()
    router = FakeRouter([route])  # type: ignore[list-item]
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    path, body = _request(Protocol.CLAUDE, alias)
    body["stream"] = True
    async with AsyncClient(
        transport=ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"x-api-key": RAW_KEY},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 502
    assert response.json()["type"] == "error"
    assert stream.closed
    assert router.failures == [81]
    assert router.successes == []
    assert audit.failed is not None
    assert billing.settlements == 1
    assert seen_payload["stream_options"] == {"include_usage": True}


async def test_read_error_after_prefetch_never_retries_another_route(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    alias = model.aliases[0].alias
    routes = [
        _route(model.id, 91, "committed", settings),
        _route(model.id, 92, "must-not-run", settings),
    ]
    first_frame = _source_frames(Protocol.OPENAI)[0]
    stream = ChunkStream((first_frame, b"unused"), fail_at=1)
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host or "")
        return httpx.Response(200, stream=stream)

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    router = FakeRouter(routes)  # type: ignore[arg-type]
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    path, body = _request(Protocol.OPENAI, alias)
    body["stream"] = True
    async with AsyncClient(
        transport=ASGITransport(app=_app(service), raise_app_exceptions=False),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200
    assert response.content == first_frame
    assert seen == ["committed.example"]
    assert stream.closed
    assert router.failures == [91]
    assert router.successes == []
    assert audit.failed is not None


async def test_incomplete_cross_protocol_eof_after_prefetch_records_failure(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    alias = model.aliases[0].alias
    route = _route(model.id, 93, "incomplete", settings)
    frames = _source_frames(Protocol.OPENAI)
    stream = ChunkStream((frames[0], frames[1], frames[-1]))

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    router = FakeRouter([route])  # type: ignore[list-item]
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: router,
    )
    path, body = _request(Protocol.CLAUDE, alias)
    body["stream"] = True
    async with AsyncClient(
        transport=ASGITransport(app=_app(service), raise_app_exceptions=False),
        base_url="http://test",
        headers={"x-api-key": RAW_KEY},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200
    assert b"message_stop" not in response.content
    assert stream.closed
    assert router.failures == [93]
    assert router.successes == []
    assert audit.completed is None
    assert audit.failed is not None


@pytest.mark.parametrize("protocol", list(Protocol))
async def test_same_protocol_truncated_eof_records_upstream_failure(
    session: AsyncSession,
    protocol: Protocol,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    alias = model.aliases[0].alias
    route = _route(model.id, 100 + list(Protocol).index(protocol), "truncated", settings, protocol)
    complete_frames = _source_frames(protocol)
    stream = ChunkStream(complete_frames[:-1])

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    route_router = FakeRouter([route])  # type: ignore[list-item]
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: route_router,
    )
    path, body = _request(protocol, alias)
    body["stream"] = True
    headers = {
        Protocol.OPENAI: {"authorization": f"Bearer {RAW_KEY}"},
        Protocol.CLAUDE: {"x-api-key": RAW_KEY},
        Protocol.GEMINI: {"x-goog-api-key": RAW_KEY},
    }[protocol]
    async with AsyncClient(
        transport=ASGITransport(app=_app(service), raise_app_exceptions=False),
        base_url="http://test",
        headers=headers,
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200
    assert response.content == b"".join(complete_frames[:-1])
    assert stream.closed
    assert route_router.successes == []
    assert route_router.failures == [route.route_id]
    assert audit.completed is None
    assert audit.failed is not None


async def test_complete_stream_retains_recovery_snapshot_when_final_settlement_fails(
    session: AsyncSession,
) -> None:
    settings = _settings()
    model = await _catalog(session)
    alias = model.aliases[0].alias
    route = _route(model.id, 110, "settlement-fails", settings)
    frames = _source_frames(Protocol.OPENAI)
    stream = ChunkStream(frames)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})

    class FailingSettlementBilling(FakeBilling):
        async def settle_request(self, **_: Any) -> SettlementResult:
            self.settlements += 1
            raise RuntimeError("database unavailable")

    billing = FailingSettlementBilling()
    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    service = GatewayService(
        session=session,
        settings=settings,
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        http_client_factory=FakeHttpClients(upstream_client),
        router_factory=lambda _: FakeRouter([route]),  # type: ignore[list-item]
    )
    path, body = _request(Protocol.OPENAI, alias)
    body["stream"] = True
    async with AsyncClient(
        transport=ASGITransport(app=_app(service), raise_app_exceptions=False),
        base_url="http://test",
        headers={"authorization": f"Bearer {RAW_KEY}"},
    ) as client:
        response = await client.post(path, json=body)
    await upstream_client.aclose()

    assert response.status_code == 200
    assert response.content == b"".join(frames)
    assert billing.reservation_recoveries[0].cost == Decimal("0")
    assert billing.recovery_updates[0].usage.output_tokens == 0
    assert billing.recovery_updates[0].cost == Decimal("0.00000010")
    assert billing.recovery_updates[-1].usage == CanonicalUsage(2, 3)
    assert billing.recovery_updates[-1].cost == Decimal("0.00000080")
    assert billing.settlements == 1
    assert audit.completed is not None
    assert audit.completed.metadata["billing_recovery_pending"] is True
