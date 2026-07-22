from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from typing import Protocol as TypingProtocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import anyio
import orjson
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol
from ai_gateway.routing.types import RouteCandidate, RouteFailure
from ai_gateway.transport.proxy import NoProxyMatcher
from ai_gateway.transport.upstream import build_upstream_headers

logger = logging.getLogger(__name__)

Frame = str | bytes
FrameObserver = Callable[[str, Frame], Awaitable[None]]
IntervalCallback = Callable[[], Awaitable[None]]
Connector = Callable[..., Any]

_CLIENT_CREDENTIAL_QUERY_KEYS = frozenset({"access_token", "api_key", "key"})
_HANDSHAKE_HEADERS = frozenset(
    {
        "host",
        "connection",
        "upgrade",
        "sec-websocket-accept",
        "sec-websocket-extensions",
        "sec-websocket-key",
        "sec-websocket-protocol",
        "sec-websocket-version",
    }
)
_ALLOWED_SUBPROTOCOLS: Mapping[Protocol, frozenset[str]] = {
    Protocol.OPENAI: frozenset({"realtime", "openai-realtime-v1"}),
    Protocol.GEMINI: frozenset({"gemini-live"}),
    Protocol.CLAUDE: frozenset(),
}
_CREDENTIAL_SUBPROTOCOL_MARKERS = (
    "api-key",
    "apikey",
    "authorization",
    "bearer",
    "credential",
    "insecure-api-key",
    "secret",
    "token",
)


class ClientWebSocket(TypingProtocol):
    @property
    def headers(self) -> Any: ...

    async def receive(self) -> MutableMapping[str, Any]: ...

    async def send_text(self, data: str) -> None: ...

    async def send_bytes(self, data: bytes) -> None: ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


class RelayHealthOutcome(StrEnum):
    NEUTRAL = "neutral"
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class RelayResult:
    client_disconnected: bool = False
    upstream_failed: bool = False
    close_code: int = 1000
    close_reason: str = ""
    exception: BaseException | None = None
    health_outcome: RelayHealthOutcome = RelayHealthOutcome.NEUTRAL
    provider_observed: bool = False
    route_failure: RouteFailure | None = None


class UpstreamWebSocketError(ConnectionError):
    def __init__(self, message: str, failure: RouteFailure) -> None:
        self.failure = failure
        super().__init__(message)


class RelayAbort(Exception):
    def __init__(self, code: int, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(reason)


class _ClientClosed(Exception):
    def __init__(self, code: int, reason: str) -> None:
        self.code = code
        self.reason = reason


class _TerminalKind(StrEnum):
    CANCELLATION = "cancellation"
    INTERNAL = "internal"
    CLIENT_DISCONNECT = "client_disconnect"
    UPSTREAM_CLOSE = "upstream_close"
    UPSTREAM_FAILURE = "upstream_failure"
    RELAY_ABORT = "relay_abort"


_TERMINAL_PRIORITY = {
    _TerminalKind.CANCELLATION: 0,
    _TerminalKind.INTERNAL: 10,
    _TerminalKind.CLIENT_DISCONNECT: 20,
    _TerminalKind.UPSTREAM_CLOSE: 30,
    _TerminalKind.UPSTREAM_FAILURE: 40,
    _TerminalKind.RELAY_ABORT: 50,
}


@dataclass(frozen=True, slots=True)
class _Terminal:
    kind: _TerminalKind
    code: int
    reason: str
    exception: BaseException | None = None
    route_failure: RouteFailure | None = None


class _TerminalCoordinator:
    def __init__(self) -> None:
        self._lock = anyio.Lock()
        self._terminal: _Terminal | None = None
        self._provider_observed = False

    async def mark_provider_observed(self) -> None:
        async with self._lock:
            self._provider_observed = True

    async def finish(self, terminal: _Terminal, task_group: anyio.abc.TaskGroup) -> None:
        with anyio.CancelScope(shield=True):
            async with self._lock:
                if (
                    self._terminal is None
                    or _TERMINAL_PRIORITY[terminal.kind] > _TERMINAL_PRIORITY[self._terminal.kind]
                ):
                    self._terminal = terminal
        task_group.cancel_scope.cancel()

    async def ensure_terminal(self, terminal: _Terminal) -> _Terminal:
        async with self._lock:
            if self._terminal is None:
                self._terminal = terminal
            return self._terminal

    async def result(self) -> RelayResult:
        async with self._lock:
            terminal = self._terminal or _Terminal(
                _TerminalKind.INTERNAL,
                1011,
                "relay terminated",
            )
            provider_observed = self._provider_observed
        if terminal.kind is _TerminalKind.UPSTREAM_FAILURE:
            health_outcome = RelayHealthOutcome.FAILURE
        elif terminal.kind is _TerminalKind.UPSTREAM_CLOSE:
            health_outcome = (
                RelayHealthOutcome.FAILURE
                if _is_abnormal_close(terminal.code)
                else (
                    RelayHealthOutcome.SUCCESS if provider_observed else RelayHealthOutcome.NEUTRAL
                )
            )
        else:
            health_outcome = RelayHealthOutcome.NEUTRAL
        client_disconnected = terminal.kind in {
            _TerminalKind.CLIENT_DISCONNECT,
            _TerminalKind.CANCELLATION,
        }
        route_failure = terminal.route_failure
        if health_outcome is RelayHealthOutcome.FAILURE and route_failure is None:
            route_failure = RouteFailure(
                error_code=f"websocket_close_{terminal.code}",
                exception=terminal.exception,
            )
        return RelayResult(
            client_disconnected=client_disconnected,
            upstream_failed=health_outcome is RelayHealthOutcome.FAILURE,
            close_code=terminal.code,
            close_reason=terminal.reason,
            exception=terminal.exception,
            health_outcome=health_outcome,
            provider_observed=provider_observed,
            route_failure=route_failure,
        )


class _CloseOnce:
    def __init__(self) -> None:
        self._lock = anyio.Lock()
        self._closed = False

    async def run(self, operation: Callable[[], Awaitable[None]]) -> None:
        async with self._lock:
            if self._closed:
                return
            try:
                await operation()
            except ConnectionClosed:
                self._closed = True
            except RuntimeError:
                self._closed = True
            else:
                self._closed = True


async def relay_websocket(
    client_ws: ClientWebSocket,
    route: RouteCandidate,
    initial_request: Frame | None,
    *,
    settings: Settings | None = None,
    query_string: str = "",
    observe_frame: FrameObserver | None = None,
    on_interval: IntervalCallback | None = None,
    interval_seconds: float = 60.0,
    subprotocols: Sequence[str] = (),
    connector: Connector = connect,
) -> RelayResult:
    """Connect one provider socket and relay frames until either peer terminates."""

    if route.websocket_url is None:
        raise ValueError("Route does not support WebSocket transport")
    active_settings = settings or get_settings()
    url = rewrite_upstream_url(route.websocket_url, query_string, route.upstream_model)
    proxy = await websocket_proxy_for(url, active_settings)
    upstream_headers = build_upstream_headers(route, client_ws.headers, settings=active_settings)
    additional_headers = [
        (name, value)
        for name, value in upstream_headers.multi_items()
        if name.lower() not in _HANDSHAKE_HEADERS
    ]
    safe_subprotocols = tuple(
        value
        for value in subprotocols
        if value in _ALLOWED_SUBPROTOCOLS[route.protocol] and not _is_credential_subprotocol(value)
    )

    try:
        upstream = await connector(
            url,
            additional_headers=additional_headers,
            subprotocols=list(safe_subprotocols) or None,
            proxy=proxy,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10,
            max_size=None,
        )
    except Exception as exc:
        raise UpstreamWebSocketError(
            "Unable to connect to upstream WebSocket",
            _connect_route_failure(exc),
        ) from exc

    coordinator = _TerminalCoordinator()
    client_close = _CloseOnce()
    upstream_close = _CloseOnce()

    async def observe(direction: str, frame: Frame) -> None:
        if observe_frame is not None:
            await observe_frame(direction, frame)

    async def finish_exception(
        exc: BaseException,
        task_group: anyio.abc.TaskGroup,
        *,
        upstream_operation: bool,
    ) -> None:
        if isinstance(exc, RelayAbort):
            await coordinator.finish(
                _Terminal(_TerminalKind.RELAY_ABORT, exc.code, exc.reason, exc),
                task_group,
            )
        elif isinstance(exc, ConnectionClosed):
            await coordinator.finish(_connection_terminal(exc, upstream), task_group)
        elif upstream_operation and isinstance(exc, (ConnectionError, OSError, TimeoutError)):
            await coordinator.finish(
                _Terminal(
                    _TerminalKind.UPSTREAM_FAILURE,
                    1011,
                    "upstream connection failed",
                    exc,
                    RouteFailure(error_code="websocket_network_error", exception=exc),
                ),
                task_group,
            )
        else:
            await coordinator.finish(
                _Terminal(_TerminalKind.INTERNAL, 1011, "relay failed", exc),
                task_group,
            )

    async def client_to_upstream(task_group: anyio.abc.TaskGroup) -> None:
        if initial_request is not None:
            try:
                await observe("client", initial_request)
                outbound_initial = (
                    initial_request
                    if _query_has_model(query_string)
                    else rewrite_initial_request(
                        initial_request,
                        route.protocol,
                        route.upstream_model,
                    )
                )
                await upstream.send(outbound_initial)
            except anyio.get_cancelled_exc_class():
                raise
            except BaseException as exc:
                await finish_exception(exc, task_group, upstream_operation=True)
                return
        while True:
            try:
                event: MutableMapping[str, Any] | None = None
                if on_interval is None:
                    event = await client_ws.receive()
                else:
                    with anyio.move_on_after(interval_seconds) as scope:
                        event = await client_ws.receive()
                    if scope.cancel_called:
                        await on_interval()
                        continue
                frame = _client_frame(event)
            except anyio.get_cancelled_exc_class():
                raise
            except _ClientClosed as exc:
                await coordinator.finish(
                    _Terminal(_TerminalKind.CLIENT_DISCONNECT, exc.code, exc.reason, exc),
                    task_group,
                )
                return
            except BaseException as exc:
                await finish_exception(exc, task_group, upstream_operation=False)
                return

            try:
                await observe("client", frame)
                await upstream.send(frame)
            except anyio.get_cancelled_exc_class():
                raise
            except BaseException as exc:
                await finish_exception(exc, task_group, upstream_operation=True)
                return

    async def upstream_to_client(task_group: anyio.abc.TaskGroup) -> None:
        while True:
            try:
                frame = await upstream.recv()
            except anyio.get_cancelled_exc_class():
                raise
            except ConnectionClosed as exc:
                await coordinator.finish(_connection_terminal(exc, upstream), task_group)
                return
            except BaseException as exc:
                await finish_exception(exc, task_group, upstream_operation=True)
                return
            await coordinator.mark_provider_observed()
            try:
                await observe("upstream", frame)
                if isinstance(frame, str):
                    await client_ws.send_text(frame)
                else:
                    await client_ws.send_bytes(frame)
            except anyio.get_cancelled_exc_class():
                raise
            except RelayAbort as exc:
                await finish_exception(exc, task_group, upstream_operation=False)
                return
            except BaseException as exc:
                await coordinator.finish(
                    _Terminal(_TerminalKind.CLIENT_DISCONNECT, 1001, "client disconnected", exc),
                    task_group,
                )
                return

    try:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(client_to_upstream, task_group)
            task_group.start_soon(upstream_to_client, task_group)
    except anyio.get_cancelled_exc_class():
        with anyio.CancelScope(shield=True):
            await coordinator.ensure_terminal(
                _Terminal(_TerminalKind.CANCELLATION, 1001, "client disconnected")
            )
        raise
    finally:
        with anyio.CancelScope(shield=True):
            terminal = await coordinator.ensure_terminal(
                _Terminal(_TerminalKind.INTERNAL, 1011, "relay terminated")
            )
        with anyio.CancelScope(shield=True):
            await _close_peer(
                client_close,
                lambda: client_ws.close(
                    code=_wire_close_code(terminal.code),
                    reason=terminal.reason,
                ),
                "client",
            )
        with anyio.CancelScope(shield=True):
            await _close_peer(
                upstream_close,
                lambda: upstream.close(
                    code=_wire_close_code(terminal.code),
                    reason=terminal.reason,
                ),
                "upstream",
            )
    return await coordinator.result()


def select_websocket_subprotocols(
    protocol: Protocol,
    raw_header: str | None,
) -> tuple[tuple[str, ...], str | None]:
    offered = tuple(
        value.strip()
        for value in (raw_header or "").split(",")
        if value.strip() and not _is_credential_subprotocol(value.strip())
    )
    allowed = tuple(value for value in offered if value in _ALLOWED_SUBPROTOCOLS[protocol])
    return allowed, allowed[0] if allowed else None


def rewrite_upstream_url(base_url: str, query_string: str, upstream_model: str) -> str:
    parsed = urlsplit(base_url)
    provider_query = parse_qsl(parsed.query, keep_blank_values=True)
    inbound_query = parse_qsl(query_string, keep_blank_values=True)
    had_model = any(name == "model" for name, _ in inbound_query)
    combined = [
        (name, value) for name, value in provider_query if not (had_model and name == "model")
    ]
    combined.extend(
        (name, value)
        for name, value in inbound_query
        if name not in _CLIENT_CREDENTIAL_QUERY_KEYS and name != "model"
    )
    if had_model:
        combined.insert(0, ("model", upstream_model))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(combined), parsed.fragment)
    )


def rewrite_initial_request(frame: Frame, protocol: Protocol, upstream_model: str) -> Frame:
    try:
        payload = orjson.loads(frame)
    except (orjson.JSONDecodeError, UnicodeDecodeError):
        return frame
    if not isinstance(payload, dict):
        return frame
    rewritten = False
    if protocol is Protocol.OPENAI:
        session = payload.get("session")
        if isinstance(session, dict) and isinstance(session.get("model"), str):
            session = session.copy()
            session["model"] = upstream_model
            payload = payload.copy()
            payload["session"] = session
            rewritten = True
        elif isinstance(payload.get("model"), str):
            payload = payload.copy()
            payload["model"] = upstream_model
            rewritten = True
    elif protocol is Protocol.GEMINI:
        setup = payload.get("setup")
        if isinstance(setup, dict) and isinstance(setup.get("model"), str):
            setup = setup.copy()
            setup["model"] = upstream_model
            payload = payload.copy()
            payload["setup"] = setup
            rewritten = True
    if not rewritten:
        return frame
    encoded = orjson.dumps(payload)
    return encoded if isinstance(frame, bytes) else encoded.decode()


async def websocket_proxy_for(url: str, settings: Settings) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"ws", "wss"} or parsed.hostname is None:
        raise ValueError("Outbound WebSocket URL must use ws or wss and include a host")
    proxy = settings.http_proxy if parsed.scheme == "ws" else settings.https_proxy
    if proxy is None and parsed.scheme == "wss":
        proxy = settings.http_proxy
    if proxy is None:
        return None
    matcher = NoProxyMatcher.from_string(settings.no_proxy)
    port = parsed.port or (80 if parsed.scheme == "ws" else 443)
    matcher_host = (
        f"[{parsed.hostname}]:{port}" if ":" in parsed.hostname else f"{parsed.hostname}:{port}"
    )
    if matcher.matches(matcher_host, ()):
        return None
    if matcher.needs_dns_resolution and _parse_ip(parsed.hostname) is None:
        if matcher.matches(matcher_host, await _resolve_host(parsed.hostname)):
            return None
    return proxy


async def _resolve_host(host: str) -> tuple[str, ...]:
    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, host, None, type=socket.SOCK_STREAM),
            timeout=2,
        )
    except (TimeoutError, OSError):
        return ()
    return tuple({str(address[0]) for *_, address in results if address})


async def _close_peer(
    close_once: _CloseOnce,
    operation: Callable[[], Awaitable[None]],
    peer: str,
) -> None:
    for attempt in range(2):
        try:
            await close_once.run(operation)
            return
        except OSError as exc:
            if attempt == 1:
                logger.warning(
                    "WebSocket close failed peer=%s exception_type=%s",
                    peer,
                    type(exc).__name__,
                )
            else:
                await anyio.sleep(0)


def _connect_route_failure(exc: BaseException) -> RouteFailure:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return RouteFailure(
        status_code=status_code if isinstance(status_code, int) else None,
        error_code="websocket_handshake" if isinstance(status_code, int) else "websocket_connect",
        exception=exc,
    )


def _connection_terminal(exc: ConnectionClosed, upstream: ClientConnection) -> _Terminal:
    code, reason = _connection_close_detail(exc, upstream)
    route_failure = (
        RouteFailure(
            error_code=f"websocket_close_{code}",
            exception=exc,
        )
        if _is_abnormal_close(code)
        else None
    )
    return _Terminal(
        _TerminalKind.UPSTREAM_CLOSE,
        code,
        reason,
        exc if route_failure is not None else None,
        route_failure,
    )


def _client_frame(event: Mapping[str, Any] | None) -> Frame:
    if event is None:
        raise _ClientClosed(1001, "client disconnected")
    if event.get("type") == "websocket.disconnect":
        code = event.get("code", 1000)
        reason = event.get("reason", "")
        raise _ClientClosed(code if isinstance(code, int) else 1000, str(reason or ""))
    text = event.get("text")
    if isinstance(text, str):
        return text
    data = event.get("bytes")
    if isinstance(data, bytes):
        return data
    raise _ClientClosed(1003, "unsupported frame")


def _connection_close_detail(exc: ConnectionClosed, upstream: ClientConnection) -> tuple[int, str]:
    code = upstream.close_code or 1006
    reason = upstream.close_reason or ""
    if exc.rcvd is not None:
        code = exc.rcvd.code
        reason = exc.rcvd.reason
    return code, reason


def _is_abnormal_close(code: int) -> bool:
    return code not in {1000, 1001}


def _wire_close_code(code: int) -> int:
    return 1011 if code in {1005, 1006, 1015} else code


def _query_has_model(query_string: str) -> bool:
    return any(name == "model" for name, _ in parse_qsl(query_string, keep_blank_values=True))


def _is_credential_subprotocol(value: str) -> bool:
    normalized = value.lower()
    return normalized.startswith("sk-") or any(
        marker in normalized for marker in _CREDENTIAL_SUBPROTOCOL_MARKERS
    )


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None
