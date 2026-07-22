from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol as TypingProtocol

import httpx
import orjson

from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol
from ai_gateway.core.security import decrypt_secret

HeaderInput = httpx.Headers | Mapping[str, str] | Sequence[tuple[str, str]]

_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_INBOUND_ONLY_HEADERS = frozenset(
    {
        "authorization",
        "x-api-key",
        "x-goog-api-key",
        "anthropic-version",
        "cookie",
        "host",
        "content-length",
    }
)


class UpstreamRoute(TypingProtocol):
    @property
    def protocol(self) -> Protocol: ...

    @property
    def base_url(self) -> str: ...

    @property
    def credential_encrypted(self) -> bytes: ...

    @property
    def extra_headers_encrypted(self) -> bytes | None: ...


def build_upstream_request(
    route: UpstreamRoute,
    inbound_headers: HeaderInput,
    body: bytes,
    *,
    settings: Settings | None = None,
    method: str = "POST",
    url: str | httpx.URL | None = None,
) -> httpx.Request:
    """Build one authenticated upstream request without forwarding client credentials."""

    headers = build_upstream_headers(route, inbound_headers, settings=settings)
    return httpx.Request(method, url or route.base_url, headers=headers, content=body)


def build_upstream_headers(
    route: UpstreamRoute,
    inbound_headers: HeaderInput,
    *,
    settings: Settings | None = None,
) -> httpx.Headers:
    """Build provider-authenticated headers shared by HTTP and WebSocket transports."""

    active_settings = settings or get_settings()
    credentials = _decrypt_json_object(route.credential_encrypted, settings=active_settings)
    configured_headers = (
        _decrypt_header_object(route.extra_headers_encrypted, settings=active_settings)
        if route.extra_headers_encrypted is not None
        else {}
    )
    headers = httpx.Headers(_sanitize_inbound_headers(inbound_headers, configured_headers))
    headers.update(_protocol_auth_headers(route.protocol, credentials))
    headers.update(configured_headers)
    return headers


def _sanitize_inbound_headers(
    inbound_headers: HeaderInput,
    configured_headers: Mapping[str, str],
) -> dict[str, str]:
    incoming = httpx.Headers(inbound_headers)
    connection_tokens = {
        token.strip().lower()
        for value in incoming.get_list("connection")
        for token in value.split(",")
        if token.strip()
    }
    configured_names = {name.lower() for name in configured_headers}
    blocked = _HOP_BY_HOP_HEADERS | _INBOUND_ONLY_HEADERS | connection_tokens | configured_names
    sanitized: dict[str, str] = {}
    for name, value in incoming.multi_items():
        if name.lower() not in blocked:
            sanitized[name] = value
    return sanitized


def _protocol_auth_headers(
    protocol: Protocol,
    credentials: Mapping[str, object],
) -> dict[str, str]:
    api_key = credentials.get("api_key")
    if not isinstance(api_key, str) or not api_key:
        raise ValueError("Provider credential must contain a non-empty api_key")
    if protocol is Protocol.OPENAI:
        return {"authorization": f"Bearer {api_key}"}
    if protocol is Protocol.CLAUDE:
        version = credentials.get("anthropic_version", "2023-06-01")
        if not isinstance(version, str) or not version:
            raise ValueError("Provider credential contains an invalid anthropic_version")
        return {"x-api-key": api_key, "anthropic-version": version}
    if protocol is Protocol.GEMINI:
        return {"x-goog-api-key": api_key}
    raise ValueError("Unsupported provider protocol")


def _decrypt_header_object(encrypted: bytes, *, settings: Settings) -> dict[str, str]:
    values = _decrypt_json_object(encrypted, settings=settings)
    if not all(isinstance(name, str) and isinstance(value, str) for name, value in values.items()):
        raise ValueError("Provider headers must be a JSON object of string values")
    return {name: value for name, value in values.items() if isinstance(value, str)}


def _decrypt_json_object(encrypted: bytes, *, settings: Settings) -> dict[str, object]:
    try:
        value = orjson.loads(decrypt_secret(encrypted, settings=settings))
    except Exception:
        raise ValueError("Provider secret could not be decoded") from None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Provider secret must be a JSON object")
    return value
