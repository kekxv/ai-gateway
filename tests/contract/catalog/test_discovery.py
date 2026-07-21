from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import cast

import httpx
import orjson
import pytest
from cryptography.fernet import Fernet

from ai_gateway.catalog.discovery import discover_models
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import Protocol
from ai_gateway.core.security import encrypt_secret
from ai_gateway.routing.types import RouteCandidate
from ai_gateway.transport.upstream import build_upstream_request


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret="discovery-contract-jwt-secret",
        encryption_key=Fernet.generate_key().decode(),
    )


def _encrypted_json(value: dict[str, str], settings: Settings) -> bytes:
    return encrypt_secret(orjson.dumps(value).decode(), settings=settings)


def _route(
    protocol: Protocol,
    settings: Settings,
    *,
    extra_headers: dict[str, str] | None = None,
) -> RouteCandidate:
    return RouteCandidate(
        route_id=1,
        model_id=1,
        provider_id=1,
        provider_protocol_id=1,
        protocol=protocol,
        base_url="https://provider.example",
        websocket_url=None,
        upstream_model="provider-model",
        weight=100,
        provider_credential_encrypted=_encrypted_json({"api_key": "provider-secret"}, settings),
        extra_headers_encrypted=(
            _encrypted_json(extra_headers, settings) if extra_headers is not None else None
        ),
    )


@pytest.mark.parametrize(
    ("protocol", "expected_headers"),
    [
        (Protocol.OPENAI, {"authorization": "Bearer provider-secret"}),
        (
            Protocol.CLAUDE,
            {"x-api-key": "provider-secret", "anthropic-version": "2023-06-01"},
        ),
        (Protocol.GEMINI, {"x-goog-api-key": "provider-secret"}),
    ],
)
def test_build_upstream_request_replaces_inbound_auth_for_each_protocol(
    protocol: Protocol,
    expected_headers: dict[str, str],
    settings: Settings,
) -> None:
    request = build_upstream_request(
        _route(protocol, settings),
        {
            "authorization": "Bearer inbound-gateway-key",
            "x-api-key": "inbound-gateway-key",
            "x-goog-api-key": "inbound-gateway-key",
            "x-request-id": "request-123",
        },
        b'{"model":"provider-model"}',
        settings=settings,
    )

    for name, value in expected_headers.items():
        assert request.headers[name] == value
    assert "inbound-gateway-key" not in str(request.headers)
    assert request.headers["x-request-id"] == "request-123"


def test_build_upstream_request_strips_hop_headers_and_merges_configured_headers(
    settings: Settings,
) -> None:
    body = b'{"model":"provider-model"}'
    request = build_upstream_request(
        _route(
            Protocol.OPENAI,
            settings,
            extra_headers={
                "Authorization": "Bearer configured-secret",
                "X-Configured": "provider-value",
            },
        ),
        {
            "Authorization": "Bearer inbound-secret",
            "X-Api-Key": "inbound-secret",
            "X-Goog-Api-Key": "inbound-secret",
            "Cookie": "session=inbound-secret",
            "Host": "attacker.example",
            "Content-Length": "9999",
            "Connection": "keep-alive, x-remove-me",
            "Keep-Alive": "timeout=5",
            "Proxy-Authenticate": "inbound-secret",
            "Proxy-Authorization": "inbound-secret",
            "TE": "trailers",
            "Trailer": "x-checksum",
            "Transfer-Encoding": "chunked",
            "Upgrade": "websocket",
            "X-Remove-Me": "dynamic-hop-header",
            "X-Configured": "inbound-value",
            "X-Preserve": "yes",
        },
        body,
        settings=settings,
    )

    assert request.headers["authorization"] == "Bearer configured-secret"
    assert request.headers["x-configured"] == "provider-value"
    assert request.headers["x-preserve"] == "yes"
    assert request.headers["content-length"] == str(len(body))
    for stripped in (
        "x-api-key",
        "x-goog-api-key",
        "cookie",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "x-remove-me",
    ):
        assert stripped not in request.headers
    assert request.url.host == "provider.example"


def _protocol(
    protocol: Protocol,
    base_url: str,
    settings: Settings,
) -> SimpleNamespace:
    provider = SimpleNamespace(
        credential_encrypted=_encrypted_json({"api_key": "discovery-secret"}, settings)
    )
    return SimpleNamespace(
        protocol=protocol,
        base_url=base_url,
        extra_headers_encrypted=None,
        provider=provider,
    )


async def _discover_with_handler(
    provider_protocol: SimpleNamespace,
    settings: Settings,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[str]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await discover_models(
            cast(object, provider_protocol),
            client=client,
            settings=settings,
        )


@pytest.mark.asyncio
async def test_openai_discovery_uses_models_endpoint_and_native_cursor(
    settings: Settings,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer discovery-secret"
        if len(requests) == 1:
            assert request.url.path == "/v1/models"
            assert request.url.params.get("after") is None
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "gpt-4.1-mini"}],
                    "has_more": True,
                    "last_id": "gpt-4.1-mini",
                },
            )
        assert request.url.path == "/v1/models"
        assert request.url.params["after"] == "gpt-4.1-mini"
        return httpx.Response(
            200,
            json={"data": [{"id": "gpt-4.1"}], "has_more": False},
        )

    models = await _discover_with_handler(
        _protocol(Protocol.OPENAI, "https://provider.example/v1", settings),
        settings,
        handler,
    )

    assert models == ["gpt-4.1-mini", "gpt-4.1"]
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_claude_discovery_uses_v1_models_and_after_id(
    settings: Settings,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["x-api-key"] == "discovery-secret"
        assert request.headers["anthropic-version"] == "2023-06-01"
        if len(requests) == 1:
            assert request.url.path == "/v1/models"
            assert request.url.params.get("after_id") is None
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "claude-sonnet-4-5"}],
                    "has_more": True,
                    "last_id": "claude-sonnet-4-5",
                },
            )
        assert request.url.params["after_id"] == "claude-sonnet-4-5"
        return httpx.Response(
            200,
            json={"data": [{"id": "claude-opus-4-1"}], "has_more": False},
        )

    models = await _discover_with_handler(
        _protocol(Protocol.CLAUDE, "https://provider.example", settings),
        settings,
        handler,
    )

    assert models == ["claude-sonnet-4-5", "claude-opus-4-1"]
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_gemini_discovery_normalizes_names_and_uses_page_token(
    settings: Settings,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["x-goog-api-key"] == "discovery-secret"
        if len(requests) == 1:
            assert request.url.path == "/v1beta/models"
            assert request.url.params.get("pageToken") is None
            return httpx.Response(
                200,
                json={
                    "models": [{"name": "models/gemini-2.5-flash"}],
                    "nextPageToken": "next-page",
                },
            )
        assert request.url.params["pageToken"] == "next-page"
        return httpx.Response(200, json={"models": [{"name": "models/gemini-2.5-pro"}]})

    models = await _discover_with_handler(
        _protocol(Protocol.GEMINI, "https://provider.example", settings),
        settings,
        handler,
    )

    assert models == ["gemini-2.5-flash", "gemini-2.5-pro"]
    assert len(requests) == 2
