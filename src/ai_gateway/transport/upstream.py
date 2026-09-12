from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Protocol as TypingProtocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import orjson

from ai_gateway.catalog.credentials import ProviderCredential
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
_CLIENT_CREDENTIAL_QUERY_NAMES = frozenset(
    {
        "key",
        "apikey",
        "accesstoken",
        "authtoken",
        "authorization",
        "password",
        "clientsecret",
        "clientcredential",
        "token",
        "secret",
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
    """Build one upstream request without forwarding client credentials."""

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
    headers.update(ProviderCredential.from_mapping(credentials).auth_headers(route.protocol))
    headers.update(configured_headers)
    return headers


def merge_upstream_query(url: str, inbound_query: str | Sequence[tuple[str, str]]) -> str:
    """Merge untrusted client query parameters without allowing credential overrides."""

    parsed = urlsplit(url)
    provider_query = parse_qsl(parsed.query, keep_blank_values=True)
    inbound = (
        parse_qsl(inbound_query, keep_blank_values=True)
        if isinstance(inbound_query, str)
        else list(inbound_query)
    )
    trusted_names = {name.casefold() for name, _ in provider_query}
    combined = list(provider_query)
    for name, value in inbound:
        normalized = re.sub(r"[^a-z0-9]", "", name.casefold())
        if normalized in _CLIENT_CREDENTIAL_QUERY_NAMES:
            continue
        if name.casefold() in trusted_names:
            continue
        combined.append((name, value))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(combined), parsed.fragment)
    )


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
