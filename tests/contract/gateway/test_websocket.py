from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import anyio
import orjson
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from starlette.datastructures import Headers, QueryParams
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from ai_gateway.audit.service import RequestContext, RequestFailure, RequestResult
from ai_gateway.auth.api_key import ApiKeyPrincipal
from ai_gateway.billing.service import (
    AdjustmentResult,
    BalanceReservation,
    InsufficientBalance,
    SettlementResult,
)
from ai_gateway.catalog.schemas import ResolvedModel
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import ApiKeyScope, Protocol
from ai_gateway.core.security import encrypt_secret
from ai_gateway.gateway.websocket import WebSocketGatewayService
from ai_gateway.routing.types import RouteCandidate, RouteFailure
from ai_gateway.transport.websocket import (
    RelayHealthOutcome,
    RelayResult,
    UpstreamWebSocketError,
    relay_websocket,
    rewrite_initial_request,
    select_websocket_subprotocols,
    websocket_proxy_for,
)


class AsyncBarrier:
    def __init__(self, parties: int) -> None:
        self.parties = parties
        self.arrivals = 0
        self.event = anyio.Event()
        self.lock = anyio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            self.arrivals += 1
            if self.arrivals == self.parties:
                self.event.set()
        await self.event.wait()


class FakeUpstreamConnection:
    def __init__(
        self,
        *,
        barrier: AsyncBarrier | None = None,
        close_code: int = 4100,
        close_reason: str = "provider-race",
        close_delay: float = 0,
        send_error: BaseException | None = None,
        recv_frame: str | bytes | None = None,
    ) -> None:
        self.barrier = barrier
        self.close_code = close_code
        self.close_reason = close_reason
        self.close_delay = close_delay
        self.send_error = send_error
        self.recv_frame = recv_frame
        self.close_calls: list[tuple[int, str]] = []
        self.sent: list[str | bytes] = []
        self.started = anyio.Event()

    async def send(self, frame: str | bytes) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(frame)

    async def recv(self) -> str | bytes:
        self.started.set()
        if self.recv_frame is not None:
            frame = self.recv_frame
            self.recv_frame = None
            return frame
        if self.barrier is not None:
            await self.barrier.wait()
            raise ConnectionClosedError(
                Close(self.close_code, self.close_reason),
                None,
            )
        await anyio.sleep_forever()
        raise AssertionError("unreachable")

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_calls.append((code, reason))
        if self.close_delay:
            await anyio.sleep(self.close_delay)


class FakeClientWebSocket:
    def __init__(self, incoming: list[dict[str, Any]], headers: dict[str, str]) -> None:
        self._incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        for event in incoming:
            self._incoming.put_nowait(event)
        self.headers = headers
        self.sent: list[str | bytes] = []
        self.close_calls: list[tuple[int, str]] = []

    async def receive(self) -> dict[str, Any]:
        return await self._incoming.get()

    async def send_text(self, value: str) -> None:
        self.sent.append(value)

    async def send_bytes(self, value: bytes) -> None:
        self.sent.append(value)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.close_calls.append((code, reason or ""))


class RacingClientWebSocket(FakeClientWebSocket):
    def __init__(self, barrier: AsyncBarrier | None = None, *, close_delay: float = 0) -> None:
        super().__init__([], {})
        self.barrier = barrier
        self.close_delay = close_delay
        self.started = anyio.Event()

    async def receive(self) -> dict[str, Any]:
        self.started.set()
        if self.barrier is not None:
            await self.barrier.wait()
            return {"type": "websocket.disconnect", "code": 1000, "reason": "client-race"}
        await anyio.sleep_forever()
        raise AssertionError("unreachable")

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.close_calls.append((code, reason or ""))
        if self.close_delay:
            await anyio.sleep(self.close_delay)


class FakeGatewayWebSocket(FakeClientWebSocket):
    def __init__(self, *, model: str = "friendly-alias") -> None:
        super().__init__([], {})
        self.headers = Headers({"authorization": "Bearer sk-gw-client-key"})
        self.query_params = QueryParams({"model": model})
        self.url = SimpleNamespace(query=f"model={model}")
        self.accept_calls = 0
        self.accepted_subprotocols: list[str | None] = []
        self.events: list[str] = []

    async def accept(self, subprotocol: str | None = None) -> None:
        self.accept_calls += 1
        self.accepted_subprotocols.append(subprotocol)
        self.events.append("accept")

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.events.append("close")
        await super().close(code, reason)


@dataclass
class FakeAudit:
    failed: RequestFailure | None = None
    completed: RequestResult | None = None

    async def start_request(
        self,
        _: RequestContext,
        __: bytes,
        *,
        request_id: Any = None,
    ) -> Any:
        return request_id

    async def fail_request(self, _: Any, failure: RequestFailure) -> None:
        self.failed = failure

    async def complete_request(self, _: Any, result: RequestResult) -> None:
        self.completed = result


class FakeSession:
    async def get(self, _: object, __: int) -> Any:
        return SimpleNamespace(
            canonical_name="canonical-model",
            input_price_per_million=Decimal("1"),
            output_price_per_million=Decimal("2"),
        )


@dataclass
class FakeBilling:
    fail_reserve: bool = False
    reserve_calls: int = 0

    default_max_output_tokens: int = 8

    async def reserve_balance(self, **_: Any) -> BalanceReservation:
        self.reserve_calls += 1
        if self.fail_reserve:
            raise InsufficientBalance(required=Decimal("1"), available=Decimal("0"))
        return BalanceReservation(1, 1, 7, "request", "key", Decimal("1"), Decimal("9"))

    async def settle_request(self, **_: Any) -> SettlementResult:
        return SettlementResult(
            1,
            "request",
            Decimal("1"),
            Decimal("0"),
            Decimal("0"),
            Decimal("9"),
            Decimal("0"),
            False,
        )

    async def update_reservation_recovery(self, **_: Any) -> bool:
        return True

    async def reconcile_charge(self, **kwargs: Any) -> AdjustmentResult:
        return AdjustmentResult(1, 1, kwargs["amount"], Decimal("9"), Decimal("0"))


class FakeRouter:
    def __init__(self, route: RouteCandidate | None = None, *, unsupported: bool = False) -> None:
        self.route = route
        self.unsupported = unsupported
        self.selection: dict[str, Any] | None = None
        self.successes: list[int] = []
        self.failures: list[tuple[int, object]] = []

    async def select_route(self, model: Any, principal: Any, protocol: Any, **kwargs: Any) -> Any:
        self.selection = {"model": model, "principal": principal, "protocol": protocol, **kwargs}
        if self.unsupported:
            from ai_gateway.routing.types import NoRouteAvailable

            raise NoRouteAvailable("friendly-alias", removed_by_transport=True)
        return self.route

    async def record_success(self, route_id: int) -> bool:
        self.successes.append(route_id)
        return True

    async def record_failure(self, route_id: int, failure: object) -> bool:
        self.failures.append((route_id, failure))
        return True


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret="websocket-contract-jwt",
        encryption_key=Fernet.generate_key().decode(),
        no_proxy="127.0.0.1,localhost",
    )


def _route(url: str, settings: Settings, protocol: Protocol = Protocol.OPENAI) -> RouteCandidate:
    return RouteCandidate(
        route_id=1,
        model_id=2,
        provider_id=3,
        provider_protocol_id=4,
        protocol=protocol,
        base_url="https://provider.example/v1",
        websocket_url=url,
        upstream_model="native-realtime-model",
        weight=100,
        provider_credential_encrypted=encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        ),
    )


@pytest.mark.asyncio
async def test_transparent_relay_rewrites_model_injects_auth_and_propagates_frames_and_close() -> (
    None
):
    settings = _settings()
    observed: dict[str, Any] = {}

    async def upstream(connection: ServerConnection) -> None:
        observed["authorization"] = connection.request.headers.get("authorization")
        observed["client_secret"] = connection.request.headers.get("x-api-key")
        observed["path"] = connection.request.path
        observed["subprotocol"] = connection.subprotocol
        observed["subprotocol_header"] = connection.request.headers.get("sec-websocket-protocol")
        observed["initial"] = await connection.recv()
        observed["binary"] = await connection.recv()
        observed["later_model"] = await connection.recv()
        await connection.send("provider-text")
        await connection.send(b"provider-bytes")
        await connection.close(4100, "provider-finished")

    async with serve(upstream, "127.0.0.1", 0, subprotocols=["realtime"]) as server:
        port = cast(Any, server).sockets[0].getsockname()[1]
        route = _route(f"ws://127.0.0.1:{port}/realtime", settings)
        client = FakeClientWebSocket(
            [
                {"type": "websocket.receive", "bytes": b"client-bytes"},
                {
                    "type": "websocket.receive",
                    "text": '{"session":{"model":"later-alias"}}',
                },
            ],
            {
                "authorization": "Bearer sk-gw-client",
                "x-api-key": "client-secret",
                "sec-websocket-protocol": (
                    "realtime, openai-insecure-api-key.sk-subprotocol-secret"
                ),
            },
        )
        initial = '{"type":"session.update","session":{"voice":"alloy"}}'

        result = await relay_websocket(
            client,  # type: ignore[arg-type]
            route,
            initial,
            settings=settings,
            query_string="model=friendly-alias&intent=transcription",
            subprotocols=("realtime", "openai-insecure-api-key.sk-subprotocol-secret"),
        )

    assert observed == {
        "authorization": "Bearer provider-secret",
        "client_secret": None,
        "path": "/realtime?model=native-realtime-model&intent=transcription",
        "subprotocol": "realtime",
        "subprotocol_header": "realtime",
        "initial": '{"type":"session.update","session":{"voice":"alloy"}}',
        "binary": b"client-bytes",
        "later_model": '{"session":{"model":"native-realtime-model"}}',
    }
    assert client.sent == ["provider-text", b"provider-bytes"]
    assert client.close_calls == [(4100, "provider-finished")]
    assert result.health_outcome is RelayHealthOutcome.NEUTRAL
    assert result.provider_observed is True
    assert result.route_failure is None


@pytest.mark.asyncio
async def test_upstream_ping_is_answered_and_connection_stays_live() -> None:
    settings = _settings()

    async def upstream(connection: ServerConnection) -> None:
        pong = await connection.ping(b"health")
        await pong
        await connection.send("pong-observed")
        await connection.close(1000, "ok")

    async with serve(upstream, "127.0.0.1", 0) as server:
        port = cast(Any, server).sockets[0].getsockname()[1]
        client = FakeClientWebSocket([], {})
        await relay_websocket(
            client,  # type: ignore[arg-type]
            _route(f"ws://127.0.0.1:{port}", settings),
            None,
            settings=settings,
        )

    assert client.sent == ["pong-observed"]
    assert client.close_calls == [(1000, "ok")]


@pytest.mark.parametrize(
    ("protocol", "payload", "expected"),
    [
        (
            Protocol.OPENAI,
            {"type": "session.update", "session": {"model": "alias"}},
            {"type": "session.update", "session": {"model": "native"}},
        ),
        (
            Protocol.GEMINI,
            {"setup": {"model": "alias", "generationConfig": {"temperature": 0.2}}},
            {"setup": {"model": "native", "generationConfig": {"temperature": 0.2}}},
        ),
    ],
)
def test_initial_session_model_is_rewritten_without_changing_frame_type(
    protocol: Protocol,
    payload: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    text = orjson.dumps(payload).decode()
    assert orjson.loads(rewrite_initial_request(text, protocol, "native")) == expected
    assert orjson.loads(rewrite_initial_request(text.encode(), protocol, "native")) == expected


@pytest.mark.asyncio
async def test_websocket_proxy_selection_matches_http_and_no_proxy_rules() -> None:
    settings = cast(
        Settings,
        SimpleNamespace(
            http_proxy="http://http-proxy.internal:8080",
            https_proxy="http://https-proxy.internal:8443",
            no_proxy="localhost,127.0.0.1",
        ),
    )
    assert await websocket_proxy_for("ws://provider.example/live", settings) == settings.http_proxy
    assert (
        await websocket_proxy_for("wss://provider.example/live", settings) == settings.https_proxy
    )
    assert await websocket_proxy_for("ws://127.0.0.1/live", settings) is None


@pytest.mark.asyncio
async def test_websocket_proxy_honors_no_proxy_cidr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_gateway.transport.websocket as transport_module

    async def resolve(_: str) -> tuple[str, ...]:
        return ("10.20.30.40",)

    monkeypatch.setattr(transport_module, "_resolve_host", resolve)
    settings = cast(
        Settings,
        SimpleNamespace(
            http_proxy="http://proxy.internal:8080",
            https_proxy=None,
            no_proxy="10.0.0.0/8",
        ),
    )
    assert await websocket_proxy_for("ws://provider.example/live", settings) is None


def test_subprotocol_filter_drops_credential_values_and_selects_protocol_identifier() -> None:
    allowed, selected = select_websocket_subprotocols(
        Protocol.OPENAI,
        "realtime, openai-insecure-api-key.sk-secret, bearer.token, unknown",
    )
    assert allowed == ("realtime",)
    assert selected == "realtime"


@pytest.mark.asyncio
async def test_simultaneous_peer_close_uses_deterministic_provider_outcome_and_closes_once() -> (
    None
):
    settings = _settings()
    barrier = AsyncBarrier(2)
    client = RacingClientWebSocket(barrier)
    upstream = FakeUpstreamConnection(barrier=barrier)

    async def connector(*_: Any, **__: Any) -> FakeUpstreamConnection:
        return upstream

    result = await relay_websocket(
        client,  # type: ignore[arg-type]
        _route("ws://provider.example/realtime", settings),
        None,
        settings=settings,
        connector=connector,
    )

    assert result.close_code == 4100
    assert result.close_reason == "provider-race"
    assert result.health_outcome is RelayHealthOutcome.NEUTRAL
    assert client.close_calls == [(4100, "provider-race")]
    assert upstream.close_calls == [(4100, "provider-race")]


@pytest.mark.asyncio
async def test_query_model_rewrites_every_protocol_model_frame() -> None:
    settings = _settings()
    client = FakeClientWebSocket(
        [
            {
                "type": "websocket.receive",
                "text": '{"type":"session.update","session":{"model":"first-alias"}}',
            },
            {
                "type": "websocket.receive",
                "text": '{"type":"session.update","session":{"model":"later-alias"}}',
            },
            {"type": "websocket.disconnect", "code": 1000},
        ],
        {},
    )
    upstream = FakeUpstreamConnection()

    async def connector(*_: Any, **__: Any) -> FakeUpstreamConnection:
        return upstream

    await relay_websocket(
        client,  # type: ignore[arg-type]
        _route("ws://provider.example/realtime", settings),
        None,
        settings=settings,
        query_string="model=friendly-alias",
        connector=connector,
    )

    assert orjson.loads(upstream.sent[0]) == {
        "type": "session.update",
        "session": {"model": "native-realtime-model"},
    }
    assert orjson.loads(upstream.sent[1]) == {
        "type": "session.update",
        "session": {"model": "native-realtime-model"},
    }


@pytest.mark.asyncio
async def test_query_model_rewrites_every_gemini_setup_frame() -> None:
    settings = _settings()
    client = FakeClientWebSocket(
        [
            {
                "type": "websocket.receive",
                "text": '{"setup":{"model":"models/first-alias"}}',
            },
            {
                "type": "websocket.receive",
                "text": '{"setup":{"model":"models/later-alias"}}',
            },
            {"type": "websocket.disconnect", "code": 1000},
        ],
        {},
    )
    upstream = FakeUpstreamConnection()

    async def connector(*_: Any, **__: Any) -> FakeUpstreamConnection:
        return upstream

    await relay_websocket(
        client,  # type: ignore[arg-type]
        _route("ws://provider.example/live", settings, Protocol.GEMINI),
        None,
        settings=settings,
        query_string="model=friendly-alias",
        connector=connector,
    )

    assert orjson.loads(upstream.sent[0]) == {"setup": {"model": "native-realtime-model"}}
    assert orjson.loads(upstream.sent[1]) == {"setup": {"model": "native-realtime-model"}}


@pytest.mark.asyncio
async def test_client_frame_is_committed_only_after_upstream_send_succeeds() -> None:
    settings = _settings()
    frame = '{"type":"input_audio_buffer.append","audio":"abc"}'
    client = FakeClientWebSocket(
        [{"type": "websocket.receive", "text": frame}],
        {},
    )
    upstream = FakeUpstreamConnection(send_error=RuntimeError("send failed"))
    authorized: list[tuple[str, str | bytes]] = []
    committed: list[tuple[str, str | bytes]] = []

    async def connector(*_: Any, **__: Any) -> FakeUpstreamConnection:
        return upstream

    async def authorize(direction: str, observed: str | bytes) -> None:
        authorized.append((direction, observed))

    async def commit(direction: str, observed: str | bytes) -> None:
        committed.append((direction, observed))

    result = await relay_websocket(
        client,  # type: ignore[arg-type]
        _route("ws://provider.example/realtime", settings),
        None,
        settings=settings,
        connector=connector,
        observe_frame=authorize,
        commit_frame=commit,
    )

    assert authorized == [("client", frame)]
    assert committed == []
    assert result.close_code == 1011


@pytest.mark.asyncio
async def test_client_commit_precedes_concurrent_upstream_observation() -> None:
    settings = _settings()
    order: list[str] = []

    class ConcurrentUpstream(FakeUpstreamConnection):
        def __init__(self) -> None:
            super().__init__()
            self.send_started = anyio.Event()
            self.frame_ready = anyio.Event()
            self.received_once = False

        async def send(self, frame: str | bytes) -> None:
            order.append("send")
            self.send_started.set()
            await self.frame_ready.wait()
            await anyio.sleep(0)
            self.sent.append(frame)

        async def recv(self) -> str:
            if self.received_once:
                raise ConnectionClosedError(Close(1000, "ok"), None)
            self.received_once = True
            await self.send_started.wait()
            self.frame_ready.set()
            return "provider-frame"

    client = FakeClientWebSocket(
        [{"type": "websocket.receive", "text": "client-frame"}],
        {},
    )
    upstream = ConcurrentUpstream()

    async def connector(*_: Any, **__: Any) -> ConcurrentUpstream:
        return upstream

    async def authorize(direction: str, _: str | bytes) -> None:
        order.append(f"authorize:{direction}")

    async def commit(direction: str, _: str | bytes) -> None:
        order.append(f"commit:{direction}")

    await relay_websocket(
        client,  # type: ignore[arg-type]
        _route("ws://provider.example/realtime", settings),
        None,
        settings=settings,
        connector=connector,
        observe_frame=authorize,
        commit_frame=commit,
    )

    assert order == [
        "authorize:client",
        "send",
        "commit:client",
        "authorize:upstream",
    ]


@pytest.mark.asyncio
async def test_upstream_observer_failure_is_internal_not_client_disconnect() -> None:
    settings = _settings()
    client = FakeClientWebSocket([], {})
    upstream = FakeUpstreamConnection(recv_frame="provider-frame")

    async def connector(*_: Any, **__: Any) -> FakeUpstreamConnection:
        return upstream

    async def observe(direction: str, _: str | bytes) -> None:
        if direction == "upstream":
            raise RuntimeError("billing observer failed")

    result = await relay_websocket(
        client,  # type: ignore[arg-type]
        _route("ws://provider.example/realtime", settings),
        None,
        settings=settings,
        connector=connector,
        observe_frame=observe,
    )

    assert result.close_code == 1011
    assert result.client_disconnected is False
    assert result.internal_failed is True
    assert result.upstream_failed is False
    assert isinstance(result.exception, RuntimeError)
    assert client.sent == []


@pytest.mark.asyncio
async def test_cancellation_shields_both_slow_peer_closes() -> None:
    settings = _settings()
    client = RacingClientWebSocket(close_delay=0.01)
    upstream = FakeUpstreamConnection(close_delay=0.01)

    async def connector(*_: Any, **__: Any) -> FakeUpstreamConnection:
        return upstream

    async def run() -> None:
        await relay_websocket(
            client,  # type: ignore[arg-type]
            _route("ws://provider.example/realtime", settings),
            None,
            settings=settings,
            connector=connector,
        )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(run)
        await client.started.wait()
        await upstream.started.wait()
        task_group.cancel_scope.cancel()

    assert client.close_calls == [(1001, "client disconnected")]
    assert upstream.close_calls == [(1001, "client disconnected")]


@pytest.mark.asyncio
async def test_handshake_status_is_preserved_as_structured_route_failure() -> None:
    settings = _settings()
    client = FakeClientWebSocket([], {})

    class HandshakeFailure(Exception):
        response = SimpleNamespace(status_code=503)

    async def connector(*_: Any, **__: Any) -> Any:
        raise HandshakeFailure

    with pytest.raises(UpstreamWebSocketError) as captured:
        await relay_websocket(
            client,  # type: ignore[arg-type]
            _route("ws://provider.example/realtime", settings),
            None,
            settings=settings,
            connector=connector,
        )

    assert captured.value.failure.status_code == 503
    assert captured.value.failure.error_code == "websocket_handshake"


@pytest.mark.asyncio
async def test_invalid_api_key_closes_4401_before_route_or_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_gateway.gateway.websocket as gateway_module

    websocket = FakeGatewayWebSocket()

    async def invalid(*_: Any, **__: Any) -> ApiKeyPrincipal:
        assert websocket.accept_calls == 0
        raise HTTPException(401, {"code": "invalid_api_key", "message": "invalid"})

    monkeypatch.setattr(gateway_module, "authenticate_api_key", invalid)
    route_router = FakeRouter(unsupported=True)
    billing = FakeBilling()
    service = WebSocketGatewayService(
        session=FakeSession(),  # type: ignore[arg-type]
        settings=_settings(),
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        router_factory=lambda _: route_router,  # type: ignore[arg-type]
    )

    await service.handle(websocket, Protocol.OPENAI)  # type: ignore[arg-type]

    assert websocket.close_calls == [(4401, '{"code":"invalid_api_key"}')]
    assert websocket.events == ["accept", "close"]
    assert route_router.selection is None
    assert billing.reserve_calls == 0


@pytest.mark.asyncio
async def test_claude_only_route_closes_unsupported_transport_before_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_gateway.gateway.websocket as gateway_module

    principal = ApiKeyPrincipal(1, 7, ApiKeyScope.PROVIDERS, provider_ids=frozenset({9}))
    websocket = FakeGatewayWebSocket()

    async def authenticated(*_: Any, **__: Any) -> ApiKeyPrincipal:
        assert websocket.accept_calls == 0
        return principal

    async def resolved(*_: Any, **__: Any) -> ResolvedModel:
        return ResolvedModel(2, "friendly-alias", "canonical-model")

    monkeypatch.setattr(gateway_module, "authenticate_api_key", authenticated)
    monkeypatch.setattr(gateway_module.CatalogRepository, "resolve_model", resolved)
    route_router = FakeRouter(unsupported=True)
    billing = FakeBilling()
    service = WebSocketGatewayService(
        session=FakeSession(),  # type: ignore[arg-type]
        settings=_settings(),
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        router_factory=lambda _: route_router,  # type: ignore[arg-type]
    )

    await service.handle(websocket, Protocol.OPENAI)  # type: ignore[arg-type]

    assert websocket.close_calls == [(4400, '{"code":"unsupported_transport"}')]
    assert route_router.selection is not None
    assert route_router.selection["principal"] is principal
    assert route_router.selection["protocol"] is Protocol.OPENAI
    assert route_router.selection["require_websocket"] is True
    assert billing.reserve_calls == 0


@pytest.mark.asyncio
async def test_insufficient_balance_closes_4402_before_upstream_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_gateway.gateway.websocket as gateway_module

    async def authenticated(*_: Any, **__: Any) -> ApiKeyPrincipal:
        return ApiKeyPrincipal(1, 7, ApiKeyScope.ALL)

    async def resolved(*_: Any, **__: Any) -> ResolvedModel:
        return ResolvedModel(2, "friendly-alias", "canonical-model")

    async def unexpected_relay(*_: Any, **__: Any) -> RelayResult:
        pytest.fail("insufficient balance must stop before upstream connect")

    monkeypatch.setattr(gateway_module, "authenticate_api_key", authenticated)
    monkeypatch.setattr(gateway_module.CatalogRepository, "resolve_model", resolved)
    monkeypatch.setattr(gateway_module, "relay_websocket", unexpected_relay)
    route_router = FakeRouter(_route("ws://provider.example/realtime", _settings()))
    billing = FakeBilling(fail_reserve=True)
    websocket = FakeGatewayWebSocket()
    service = WebSocketGatewayService(
        session=FakeSession(),  # type: ignore[arg-type]
        settings=_settings(),
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        router_factory=lambda _: route_router,  # type: ignore[arg-type]
    )

    await service.handle(websocket, Protocol.OPENAI)  # type: ignore[arg-type]

    assert websocket.close_calls == [(4402, '{"code":"insufficient_balance"}')]
    assert billing.reserve_calls == 1


@pytest.mark.asyncio
async def test_client_disconnect_is_health_neutral_and_final_audit_is_disconnected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_gateway.gateway.websocket as gateway_module

    async def authenticated(*_: Any, **__: Any) -> ApiKeyPrincipal:
        return ApiKeyPrincipal(1, 7, ApiKeyScope.ALL)

    async def resolved(*_: Any, **__: Any) -> ResolvedModel:
        return ResolvedModel(2, "friendly-alias", "canonical-model")

    async def disconnected(*_: Any, **__: Any) -> RelayResult:
        return RelayResult(
            client_disconnected=True,
            close_code=1001,
            close_reason="client disconnected",
            health_outcome=RelayHealthOutcome.NEUTRAL,
        )

    monkeypatch.setattr(gateway_module, "authenticate_api_key", authenticated)
    monkeypatch.setattr(gateway_module.CatalogRepository, "resolve_model", resolved)
    monkeypatch.setattr(gateway_module, "relay_websocket", disconnected)
    route_router = FakeRouter(_route("ws://provider.example/realtime", _settings()))
    audit = FakeAudit()
    websocket = FakeGatewayWebSocket()
    service = WebSocketGatewayService(
        session=FakeSession(),  # type: ignore[arg-type]
        settings=_settings(),
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        router_factory=lambda _: route_router,  # type: ignore[arg-type]
    )

    await service.handle(websocket, Protocol.OPENAI)  # type: ignore[arg-type]

    assert route_router.successes == []
    assert route_router.failures == []
    assert audit.failed is not None
    assert audit.failed.client_disconnected is True
    assert audit.completed is None


@pytest.mark.asyncio
async def test_internal_relay_failure_audits_internal_error_not_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_gateway.gateway.websocket as gateway_module

    async def authenticated(*_: Any, **__: Any) -> ApiKeyPrincipal:
        return ApiKeyPrincipal(1, 7, ApiKeyScope.ALL)

    async def resolved(*_: Any, **__: Any) -> ResolvedModel:
        return ResolvedModel(2, "friendly-alias", "canonical-model")

    failure = RuntimeError("billing observer failed")

    async def failed(*_: Any, **__: Any) -> RelayResult:
        return RelayResult(
            internal_failed=True,
            close_code=1011,
            close_reason="relay failed",
            exception=failure,
        )

    monkeypatch.setattr(gateway_module, "authenticate_api_key", authenticated)
    monkeypatch.setattr(gateway_module.CatalogRepository, "resolve_model", resolved)
    monkeypatch.setattr(gateway_module, "relay_websocket", failed)
    audit = FakeAudit()
    service = WebSocketGatewayService(
        session=FakeSession(),  # type: ignore[arg-type]
        settings=_settings(),
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        router_factory=lambda _: FakeRouter(_route("ws://provider.example/realtime", _settings())),  # type: ignore[arg-type]
    )

    await service.handle(FakeGatewayWebSocket(), Protocol.OPENAI)  # type: ignore[arg-type]

    assert audit.failed is not None
    assert audit.failed.error_code == "internal_error"
    assert audit.failed.client_disconnected is False


@pytest.mark.asyncio
async def test_provider_observed_success_negotiates_safe_subprotocol_and_completes_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_gateway.gateway.websocket as gateway_module

    async def authenticated(*_: Any, **__: Any) -> ApiKeyPrincipal:
        return ApiKeyPrincipal(1, 7, ApiKeyScope.ALL)

    async def resolved(*_: Any, **__: Any) -> ResolvedModel:
        return ResolvedModel(2, "friendly-alias", "canonical-model")

    async def succeeded(*_: Any, **kwargs: Any) -> RelayResult:
        assert kwargs["subprotocols"] == ("realtime",)
        return RelayResult(
            close_code=1000,
            close_reason="ok",
            health_outcome=RelayHealthOutcome.SUCCESS,
            provider_observed=True,
        )

    monkeypatch.setattr(gateway_module, "authenticate_api_key", authenticated)
    monkeypatch.setattr(gateway_module.CatalogRepository, "resolve_model", resolved)
    monkeypatch.setattr(gateway_module, "relay_websocket", succeeded)
    route_router = FakeRouter(_route("ws://provider.example/realtime", _settings()))
    audit = FakeAudit()
    websocket = FakeGatewayWebSocket()
    websocket.headers = Headers(
        {
            "authorization": "Bearer sk-gw-client-key",
            "sec-websocket-protocol": "realtime, openai-insecure-api-key.sk-secret",
        }
    )
    service = WebSocketGatewayService(
        session=FakeSession(),  # type: ignore[arg-type]
        settings=_settings(),
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        router_factory=lambda _: route_router,  # type: ignore[arg-type]
    )

    await service.handle(websocket, Protocol.OPENAI)  # type: ignore[arg-type]

    assert websocket.accepted_subprotocols == ["realtime"]
    assert route_router.successes == [1]
    assert route_router.failures == []
    assert audit.completed is not None
    assert audit.failed is None


@pytest.mark.asyncio
async def test_handshake_failure_penalizes_health_and_fails_final_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_gateway.gateway.websocket as gateway_module

    async def authenticated(*_: Any, **__: Any) -> ApiKeyPrincipal:
        return ApiKeyPrincipal(1, 7, ApiKeyScope.ALL)

    async def resolved(*_: Any, **__: Any) -> ResolvedModel:
        return ResolvedModel(2, "friendly-alias", "canonical-model")

    failure = RouteFailure(status_code=503, error_code="websocket_handshake")

    async def failed(*_: Any, **__: Any) -> RelayResult:
        from ai_gateway.transport.websocket import UpstreamWebSocketError

        raise UpstreamWebSocketError("handshake failed", failure)

    monkeypatch.setattr(gateway_module, "authenticate_api_key", authenticated)
    monkeypatch.setattr(gateway_module.CatalogRepository, "resolve_model", resolved)
    monkeypatch.setattr(gateway_module, "relay_websocket", failed)
    route_router = FakeRouter(_route("ws://provider.example/realtime", _settings()))
    audit = FakeAudit()
    websocket = FakeGatewayWebSocket()
    service = WebSocketGatewayService(
        session=FakeSession(),  # type: ignore[arg-type]
        settings=_settings(),
        billing_service=FakeBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        router_factory=lambda _: route_router,  # type: ignore[arg-type]
    )

    await service.handle(websocket, Protocol.OPENAI)  # type: ignore[arg-type]

    assert route_router.successes == []
    assert route_router.failures == [(1, failure)]
    assert audit.failed is not None
    assert audit.completed is None


@pytest.mark.asyncio
async def test_persistent_billing_cleanup_failure_uses_specific_audit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_gateway.gateway.websocket as gateway_module

    async def authenticated(*_: Any, **__: Any) -> ApiKeyPrincipal:
        return ApiKeyPrincipal(1, 7, ApiKeyScope.ALL)

    async def resolved(*_: Any, **__: Any) -> ResolvedModel:
        return ResolvedModel(2, "friendly-alias", "canonical-model")

    async def succeeded(*_: Any, **__: Any) -> RelayResult:
        return RelayResult(
            close_code=1000,
            health_outcome=RelayHealthOutcome.SUCCESS,
            provider_observed=True,
        )

    class FailingBilling(FakeBilling):
        async def settle_request(self, **_: Any) -> SettlementResult:
            raise RuntimeError("persistent settlement failure")

    monkeypatch.setattr(gateway_module, "authenticate_api_key", authenticated)
    monkeypatch.setattr(gateway_module.CatalogRepository, "resolve_model", resolved)
    monkeypatch.setattr(gateway_module, "relay_websocket", succeeded)
    audit = FakeAudit()
    service = WebSocketGatewayService(
        session=FakeSession(),  # type: ignore[arg-type]
        settings=_settings(),
        billing_service=FailingBilling(),  # type: ignore[arg-type]
        audit_service=audit,  # type: ignore[arg-type]
        router_factory=lambda _: FakeRouter(_route("ws://provider.example/realtime", _settings())),  # type: ignore[arg-type]
    )

    await service.handle(FakeGatewayWebSocket(), Protocol.OPENAI)  # type: ignore[arg-type]

    assert audit.failed is not None
    assert audit.failed.error_code == "billing_cleanup_failed"
    assert audit.failed.metadata["billing_recovery_pending"] == "true"
