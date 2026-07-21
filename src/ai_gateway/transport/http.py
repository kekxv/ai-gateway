from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import Protocol

import httpx

from ai_gateway.transport.proxy import NoProxyMatcher

logger = logging.getLogger(__name__)

_DNS_TIMEOUT_SECONDS = 2.0
_CLIENT_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=300.0, pool=10.0)
_CLIENT_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=30.0,
)


class ProxySettings(Protocol):
    http_proxy: str | None
    https_proxy: str | None
    no_proxy: str


class HttpClientFactory:
    """Owns reusable direct and proxy-specific ``httpx`` client pools."""

    def __init__(self, settings: ProxySettings) -> None:
        self._no_proxy = NoProxyMatcher.from_string(settings.no_proxy)
        self._closed = False
        self._clients: list[httpx.AsyncClient] = []

        http_proxy, self._http_proxy_label = _parse_proxy(settings.http_proxy, label="HTTP")
        https_proxy, self._https_proxy_label = _parse_proxy(settings.https_proxy, label="HTTPS")

        self._direct_client = self._new_client()
        self._http_proxy_client = self._new_client(proxy=http_proxy) if http_proxy else None
        self._https_proxy_client = self._new_client(proxy=https_proxy) if https_proxy else None

        logger.debug(
            "Configured outbound HTTP clients: http=%s https=%s",
            self._http_proxy_label or "direct",
            self._https_proxy_label or self._http_proxy_label or "direct",
        )

    def __repr__(self) -> str:
        http_target = self._http_proxy_label or "direct"
        https_target = self._https_proxy_label or self._http_proxy_label or "direct"
        return (
            f"{type(self).__name__}(http={http_target!r}, "
            f"https={https_target!r}, closed={self._closed!r})"
        )

    async def client_for(self, url: str | httpx.URL) -> httpx.AsyncClient:
        """Return the existing client pool selected for an outbound URL."""

        if self._closed:
            raise RuntimeError("HTTP client factory is closed")

        parsed_url = _parse_outbound_url(url)
        if not parsed_url.host:
            raise ValueError("Outbound HTTP URL must include a host")

        proxy_client = self._proxy_client_for_scheme(parsed_url.scheme)
        if proxy_client is None:
            return self._direct_client

        host = parsed_url.host
        matcher_host = _host_with_port(host, _effective_port(parsed_url))
        if self._no_proxy.matches(matcher_host, ()):
            return self._direct_client

        if self._no_proxy.needs_dns_resolution and _parse_ip(host) is None:
            resolved_ips = await _resolve_host(host)
            if self._no_proxy.matches(matcher_host, resolved_ips):
                return self._direct_client

        return proxy_client

    async def aclose(self) -> None:
        """Close every owned pool once, even when called repeatedly."""

        if self._closed:
            return
        self._closed = True
        await asyncio.gather(*(client.aclose() for client in self._clients))

    def _proxy_client_for_scheme(self, scheme: str) -> httpx.AsyncClient | None:
        if scheme == "http":
            return self._http_proxy_client
        if scheme == "https":
            return self._https_proxy_client or self._http_proxy_client
        raise ValueError(f"Unsupported outbound URL scheme: {scheme!r}")

    def _new_client(self, *, proxy: httpx.Proxy | None = None) -> httpx.AsyncClient:
        client = httpx.AsyncClient(
            http2=True,
            limits=_CLIENT_LIMITS,
            timeout=_CLIENT_TIMEOUT,
            proxy=proxy,
            trust_env=False,
        )
        self._clients.append(client)
        return client


async def _resolve_host(host: str) -> tuple[str, ...]:
    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, host, None, type=socket.SOCK_STREAM),
            timeout=_DNS_TIMEOUT_SECONDS,
        )
    except (TimeoutError, OSError):
        return ()

    addresses: set[str] = set()
    for *_, socket_address in results:
        if socket_address:
            addresses.add(str(socket_address[0]))
    return tuple(addresses)


def _parse_outbound_url(value: str | httpx.URL) -> httpx.URL:
    try:
        parsed = value if isinstance(value, httpx.URL) else httpx.URL(value)
    except Exception as exc:
        raise ValueError(f"Invalid outbound URL: {type(exc).__name__}") from None
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported outbound URL scheme: {parsed.scheme!r}")
    return parsed


def _redacted_proxy_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        return str(httpx.URL(value).copy_with(userinfo=None))
    except Exception:
        return "<redacted>"


def _parse_proxy(value: str | None, *, label: str) -> tuple[httpx.Proxy | None, str | None]:
    if value is None or not value.strip():
        return None, None

    safe_url = _redacted_proxy_url(value) or "<redacted>"
    try:
        url = httpx.URL(value)
        if not url.scheme or not url.host:
            raise ValueError("proxy URL requires a scheme and host")
        return httpx.Proxy(url), safe_url
    except Exception as exc:
        raise ValueError(
            f"Unable to configure {label} proxy {safe_url}: {type(exc).__name__}"
        ) from None


def _host_with_port(host: str, port: int | None) -> str:
    if port is None:
        return host
    if ":" in host:
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def _effective_port(url: httpx.URL) -> int:
    if url.port is not None:
        return url.port
    return 80 if url.scheme == "http" else 443


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None
