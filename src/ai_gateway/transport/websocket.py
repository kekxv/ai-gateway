from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any
from typing import Protocol as TypingProtocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import anyio
import orjson
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol
from ai_gateway.routing.types import RouteCandidate
from ai_gateway.transport.proxy import NoProxyMatcher
from ai_gateway.transport.upstream import build_upstream_headers

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


class ClientWebSocket(TypingProtocol):
    @property
    def headers(self) -> Any: ...

    async def receive(self) -> MutableMapping[str, Any]: ...

    async def send_text(self, data: str) -> None: ...

    async def send_bytes(self, data: bytes) -> None: ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


@dataclass(frozen=True, slots=True)
class RelayResult:
    client_disconnected: bool = False
    upstream_failed: bool = False
    close_code: int = 1000
    close_reason: str = ""
    exception: BaseException | None = None


class UpstreamWebSocketError(ConnectionError):
    pass


class RelayAbort(Exception):
    def __init__(self, code: int, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(reason)


class _ClientClosed(Exception):
    def __init__(self, code: int, reason: str) -> None:
        self.code = code
        self.reason = reason


class _CloseOnce:
    def __init__(self) -> None:
        self._lock = anyio.Lock()
        self._closed = False

    async def run(self, operation: Callable[[], Awaitable[None]]) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                await operation()
            except (ConnectionClosed, OSError, RuntimeError):
                pass


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
    subprotocol_header = _header_value(client_ws.headers, "sec-websocket-protocol")
    subprotocols = (
        [value.strip() for value in subprotocol_header.split(",") if value.strip()]
        if subprotocol_header
        else None
    )

    try:
        upstream = await connector(
            url,
            additional_headers=additional_headers,
            subprotocols=subprotocols,
            proxy=proxy,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10,
            max_size=None,
        )
    except Exception as exc:
        raise UpstreamWebSocketError("Unable to connect to upstream WebSocket") from exc

    client_close = _CloseOnce()
    upstream_close = _CloseOnce()
    result = RelayResult()

    async def close_client(code: int, reason: str) -> None:
        await client_close.run(lambda: client_ws.close(code=_wire_close_code(code), reason=reason))

    async def close_upstream(code: int, reason: str) -> None:
        await upstream_close.run(lambda: upstream.close(code=_wire_close_code(code), reason=reason))

    async def observe(direction: str, frame: Frame) -> None:
        if observe_frame is not None:
            await observe_frame(direction, frame)

    async def client_to_upstream(task_group: anyio.abc.TaskGroup) -> None:
        nonlocal result
        try:
            while True:
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
                await observe("client", frame)
                await upstream.send(
                    rewrite_initial_request(frame, route.protocol, route.upstream_model)
                )
        except _ClientClosed as exc:
            result = RelayResult(True, False, exc.code, exc.reason)
            await close_upstream(exc.code, exc.reason)
        except RelayAbort as exc:
            result = RelayResult(False, False, exc.code, exc.reason, exc)
            await close_client(exc.code, exc.reason)
            await close_upstream(exc.code, exc.reason)
        except BaseException as exc:
            if isinstance(exc, anyio.get_cancelled_exc_class()):
                return
            upstream_failure = isinstance(exc, (ConnectionClosed, ConnectionError, OSError))
            result = RelayResult(not upstream_failure, upstream_failure, 1011, "relay failed", exc)
            if upstream_failure:
                await close_client(1011, "upstream connection failed")
            else:
                await close_client(1011, "relay failed")
                await close_upstream(1001, "client disconnected")
        finally:
            task_group.cancel_scope.cancel()

    async def upstream_to_client(task_group: anyio.abc.TaskGroup) -> None:
        nonlocal result
        try:
            while True:
                frame = await upstream.recv()
                await observe("upstream", frame)
                if isinstance(frame, str):
                    await client_ws.send_text(frame)
                else:
                    await client_ws.send_bytes(frame)
        except ConnectionClosed as exc:
            code, reason = _connection_close_detail(exc, upstream)
            upstream_failed = _is_network_close(code)
            result = RelayResult(
                False,
                upstream_failed,
                code,
                reason,
                exc if upstream_failed else None,
            )
            await close_client(code, reason)
        except RelayAbort as exc:
            result = RelayResult(False, False, exc.code, exc.reason, exc)
            await close_client(exc.code, exc.reason)
            await close_upstream(exc.code, exc.reason)
        except BaseException as exc:
            if isinstance(exc, anyio.get_cancelled_exc_class()):
                return
            upstream_failure = isinstance(exc, (ConnectionError, OSError))
            result = RelayResult(not upstream_failure, upstream_failure, 1011, "relay failed", exc)
            await close_client(1011 if upstream_failure else 1001, "upstream connection failed")
        finally:
            task_group.cancel_scope.cancel()

    try:
        if initial_request is not None:
            await observe("client", initial_request)
            await upstream.send(
                rewrite_initial_request(initial_request, route.protocol, route.upstream_model)
            )
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(client_to_upstream, task_group)
            task_group.start_soon(upstream_to_client, task_group)
    finally:
        with anyio.CancelScope(shield=True):
            await close_upstream(result.close_code, result.close_reason)
    return result


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


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


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


def _is_network_close(code: int) -> bool:
    return code in {1002, 1006, 1011, 1012, 1013, 1014, 1015}


def _wire_close_code(code: int) -> int:
    return 1011 if code in {1005, 1006, 1015} else code


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    for header_name, value in headers.items():
        if header_name.lower() == name:
            return value
    return None
