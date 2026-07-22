from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import orjson
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from starlette.datastructures import Headers, QueryParams
from websockets.asyncio.server import ServerConnection, serve

from ai_gateway.audit.service import RequestContext, RequestFailure, RequestResult
from ai_gateway.auth.api_key import ApiKeyPrincipal
from ai_gateway.billing.service import BalanceReservation, InsufficientBalance, SettlementResult
from ai_gateway.catalog.schemas import ResolvedModel
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import ApiKeyScope, Protocol
from ai_gateway.core.security import encrypt_secret
from ai_gateway.gateway.websocket import WebSocketGatewayService
from ai_gateway.routing.types import RouteCandidate
from ai_gateway.transport.websocket import (
    RelayResult,
    relay_websocket,
    rewrite_initial_request,
    websocket_proxy_for,
)


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


class FakeGatewayWebSocket(FakeClientWebSocket):
    def __init__(self, *, model: str = "friendly-alias") -> None:
        super().__init__([], {})
        self.headers = Headers({"authorization": "Bearer sk-gw-client-key"})
        self.query_params = QueryParams({"model": model})
        self.url = SimpleNamespace(query=f"model={model}")
        self.accept_calls = 0

    async def accept(self) -> None:
        self.accept_calls += 1


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


class FakeRouter:
    def __init__(self, route: RouteCandidate | None = None, *, unsupported: bool = False) -> None:
        self.route = route
        self.unsupported = unsupported
        self.selection: dict[str, Any] | None = None

    async def select_route(self, model: Any, principal: Any, protocol: Any, **kwargs: Any) -> Any:
        self.selection = {"model": model, "principal": principal, "protocol": protocol, **kwargs}
        if self.unsupported:
            from ai_gateway.routing.types import NoRouteAvailable

            raise NoRouteAvailable("friendly-alias", removed_by_transport=True)
        return self.route

    async def record_success(self, _: int) -> bool:
        return True

    async def record_failure(self, _: int, __: object) -> bool:
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
        observed["initial"] = await connection.recv()
        observed["binary"] = await connection.recv()
        await connection.send("provider-text")
        await connection.send(b"provider-bytes")
        await connection.close(4100, "provider-finished")

    async with serve(upstream, "127.0.0.1", 0) as server:
        port = cast(Any, server).sockets[0].getsockname()[1]
        route = _route(f"ws://127.0.0.1:{port}/realtime", settings)
        client = FakeClientWebSocket(
            [{"type": "websocket.receive", "bytes": b"client-bytes"}],
            {"authorization": "Bearer sk-gw-client", "x-api-key": "client-secret"},
        )
        initial = '{"type":"session.update","session":{"model":"friendly-alias"}}'

        await relay_websocket(
            client,  # type: ignore[arg-type]
            route,
            initial,
            settings=settings,
            query_string="model=friendly-alias&intent=transcription",
        )

    assert observed == {
        "authorization": "Bearer provider-secret",
        "client_secret": None,
        "path": "/realtime?model=native-realtime-model&intent=transcription",
        "initial": '{"type":"session.update","session":{"model":"native-realtime-model"}}',
        "binary": b"client-bytes",
    }
    assert client.sent == ["provider-text", b"provider-bytes"]
    assert client.close_calls == [(4100, "provider-finished")]


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
async def test_invalid_api_key_closes_4401_before_route_or_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_gateway.gateway.websocket as gateway_module

    async def invalid(*_: Any, **__: Any) -> ApiKeyPrincipal:
        raise HTTPException(401, {"code": "invalid_api_key", "message": "invalid"})

    monkeypatch.setattr(gateway_module, "authenticate_api_key", invalid)
    route_router = FakeRouter(unsupported=True)
    billing = FakeBilling()
    websocket = FakeGatewayWebSocket()
    service = WebSocketGatewayService(
        session=FakeSession(),  # type: ignore[arg-type]
        settings=_settings(),
        billing_service=billing,  # type: ignore[arg-type]
        audit_service=FakeAudit(),  # type: ignore[arg-type]
        router_factory=lambda _: route_router,  # type: ignore[arg-type]
    )

    await service.handle(websocket, Protocol.OPENAI)  # type: ignore[arg-type]

    assert websocket.close_calls == [(4401, '{"code":"invalid_api_key"}')]
    assert route_router.selection is None
    assert billing.reserve_calls == 0


@pytest.mark.asyncio
async def test_claude_only_route_closes_unsupported_transport_before_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_gateway.gateway.websocket as gateway_module

    principal = ApiKeyPrincipal(1, 7, ApiKeyScope.PROVIDERS, provider_ids=frozenset({9}))

    async def authenticated(*_: Any, **__: Any) -> ApiKeyPrincipal:
        return principal

    async def resolved(*_: Any, **__: Any) -> ResolvedModel:
        return ResolvedModel(2, "friendly-alias", "canonical-model")

    monkeypatch.setattr(gateway_module, "authenticate_api_key", authenticated)
    monkeypatch.setattr(gateway_module.CatalogRepository, "resolve_model", resolved)
    route_router = FakeRouter(unsupported=True)
    billing = FakeBilling()
    websocket = FakeGatewayWebSocket()
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
