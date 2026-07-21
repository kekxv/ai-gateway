from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast
from typing import Protocol as TypingProtocol

import httpx

from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol
from ai_gateway.transport.upstream import build_upstream_request


class ProviderRecord(TypingProtocol):
    @property
    def credential_encrypted(self) -> bytes: ...


class DiscoverableProtocol(TypingProtocol):
    @property
    def protocol(self) -> Protocol: ...

    @property
    def base_url(self) -> str: ...

    @property
    def extra_headers_encrypted(self) -> bytes | None: ...

    @property
    def provider(self) -> ProviderRecord: ...


class AsyncHttpClient(TypingProtocol):
    async def send(self, request: httpx.Request) -> httpx.Response: ...


@dataclass(frozen=True, slots=True)
class _DiscoveryRoute:
    protocol: Protocol
    base_url: str
    credential_encrypted: bytes
    extra_headers_encrypted: bytes | None


async def discover_models(
    provider_protocol: DiscoverableProtocol,
    *,
    client: AsyncHttpClient | None = None,
    settings: Settings | None = None,
) -> list[str]:
    """Fetch and normalize every model exposed by one provider protocol."""

    reusable_client = (
        client if client is not None else getattr(provider_protocol, "discovery_client", None)
    )
    if reusable_client is None or not callable(getattr(reusable_client, "send", None)):
        raise RuntimeError("Model discovery requires a lifespan-owned HTTP client")
    active_settings = settings or get_settings()
    route = _DiscoveryRoute(
        protocol=provider_protocol.protocol,
        base_url=provider_protocol.base_url,
        credential_encrypted=provider_protocol.provider.credential_encrypted,
        extra_headers_encrypted=provider_protocol.extra_headers_encrypted,
    )
    url = discovery_url(provider_protocol)
    params: dict[str, str] = {}
    seen_tokens: set[str] = set()
    models: list[str] = []
    seen_models: set[str] = set()

    while True:
        request_url = httpx.URL(url, params=params)
        request = build_upstream_request(
            route,
            {},
            b"",
            settings=active_settings,
            method="GET",
            url=request_url,
        )
        response = await reusable_client.send(request)
        response.raise_for_status()
        page = _json_object(response)
        for name in _page_models(provider_protocol.protocol, page):
            if name not in seen_models:
                seen_models.add(name)
                models.append(name)

        next_parameter = _next_page_parameter(provider_protocol.protocol, page)
        if next_parameter is None:
            return models
        parameter_name, token = next_parameter
        if token in seen_tokens:
            raise ValueError("Provider discovery returned a repeated page token")
        seen_tokens.add(token)
        params = {parameter_name: token}


def discovery_url(provider_protocol: DiscoverableProtocol) -> str:
    protocol = provider_protocol.protocol
    base_url = provider_protocol.base_url
    base = base_url.rstrip("/")
    if protocol is Protocol.OPENAI:
        return f"{base}/models"
    if protocol is Protocol.CLAUDE:
        return f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
    if protocol is Protocol.GEMINI:
        return f"{base}/models" if base.endswith("/v1beta") else f"{base}/v1beta/models"
    raise ValueError("Unsupported provider protocol")


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError:
        raise ValueError("Provider discovery returned invalid JSON") from None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Provider discovery response must be a JSON object")
    return cast(dict[str, Any], value)


def _page_models(protocol: Protocol, page: Mapping[str, Any]) -> list[str]:
    collection_name = "models" if protocol is Protocol.GEMINI else "data"
    raw_models = page.get(collection_name)
    if not isinstance(raw_models, list):
        raise ValueError("Provider discovery response is missing its model list")
    field_name = "name" if protocol is Protocol.GEMINI else "id"
    models: list[str] = []
    for raw_model in raw_models:
        if not isinstance(raw_model, Mapping):
            raise ValueError("Provider discovery returned an invalid model entry")
        name = raw_model.get(field_name)
        if not isinstance(name, str) or not name:
            raise ValueError("Provider discovery returned a model without an identifier")
        if protocol is Protocol.GEMINI and name.startswith("models/"):
            name = name.removeprefix("models/")
        if name:
            models.append(name)
    return models


def _next_page_parameter(
    protocol: Protocol,
    page: Mapping[str, Any],
) -> tuple[str, str] | None:
    if protocol is Protocol.GEMINI:
        token = page.get("nextPageToken")
        return ("pageToken", token) if isinstance(token, str) and token else None

    has_more = page.get("has_more", False)
    if has_more is not True:
        return None
    token = page.get("last_id") or page.get("next_cursor")
    if not isinstance(token, str) or not token:
        raise ValueError("Provider discovery indicated another page without a cursor")
    return ("after" if protocol is Protocol.OPENAI else "after_id", token)
