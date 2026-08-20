from __future__ import annotations

import httpx
import pytest
from pydantic import TypeAdapter, ValidationError

from ai_gateway.transport.provider_proxy import (
    ProviderProxyConfig,
    ProviderProxyCustom,
    proxy_summary,
    to_httpx_proxy,
    validate_proxy_websocket_compatibility,
)

PROXY_ADAPTER = TypeAdapter(ProviderProxyConfig)


def test_proxy_modes_are_discriminated_and_custom_url_is_normalized() -> None:
    assert PROXY_ADAPTER.validate_python({"mode": "inherit"}).mode == "inherit"
    assert PROXY_ADAPTER.validate_python({"mode": "direct"}).mode == "direct"

    custom = PROXY_ADAPTER.validate_python(
        {"mode": "custom", "url": " HTTP://proxy.example:8080/ "}
    )

    assert isinstance(custom, ProviderProxyCustom)
    assert custom.url == "http://proxy.example:8080"


@pytest.mark.parametrize(
    "url",
    [
        "socks5://proxy.example:1080",
        "http:///missing-host",
        "http://user:password@proxy.example:8080",
        "http://proxy.example:8080/path",
        "http://proxy.example:8080?token=secret",
        "http://proxy.example:8080/#fragment",
    ],
)
def test_custom_proxy_rejects_unsupported_or_credential_bearing_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        PROXY_ADAPTER.validate_python({"mode": "custom", "url": url})


def test_basic_auth_builds_httpx_proxy_without_putting_credentials_in_url() -> None:
    config = PROXY_ADAPTER.validate_python(
        {
            "mode": "custom",
            "url": "https://proxy.example:8443",
            "auth": {"type": "basic", "username": "proxy user", "password": "p@ss word"},
        }
    )

    proxy = to_httpx_proxy(config)

    assert isinstance(proxy, httpx.Proxy)
    assert str(proxy.url) == "https://proxy.example:8443"
    assert proxy.auth == ("proxy user", "p@ss word")
    assert "proxy user" not in repr(config)
    assert "p@ss word" not in repr(config)


def test_custom_auth_builds_httpx_proxy_headers() -> None:
    config = PROXY_ADAPTER.validate_python(
        {
            "mode": "custom",
            "url": "http://proxy.example:8080",
            "auth": {
                "type": "headers",
                "headers": {
                    "Proxy-Authorization": "Bearer proxy-secret",
                    "X-Proxy-Tenant": "north",
                },
            },
        }
    )

    proxy = to_httpx_proxy(config)

    assert isinstance(proxy, httpx.Proxy)
    assert proxy.headers["Proxy-Authorization"] == "Bearer proxy-secret"
    assert proxy.headers["X-Proxy-Tenant"] == "north"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("Host", "proxy.example"),
        ("Content-Length", "1"),
        ("Connection", "close"),
        ("Bad Header", "value"),
        ("X-Proxy", "value\r\ninjected: yes"),
    ],
)
def test_custom_auth_rejects_unsafe_headers(name: str, value: str) -> None:
    with pytest.raises(ValidationError):
        PROXY_ADAPTER.validate_python(
            {
                "mode": "custom",
                "url": "http://proxy.example:8080",
                "auth": {"type": "headers", "headers": {name: value}},
            }
        )


def test_response_summary_does_not_expose_basic_credentials() -> None:
    config = PROXY_ADAPTER.validate_python(
        {
            "mode": "custom",
            "url": "http://proxy.example:8080",
            "auth": {"type": "basic", "username": "secret-user", "password": "secret-pass"},
        }
    )

    summary = proxy_summary(config)

    assert summary.model_dump() == {
        "mode": "custom",
        "url": "http://proxy.example:8080",
        "auth_type": "basic",
        "has_auth": True,
    }
    assert "secret-user" not in repr(summary)
    assert "secret-pass" not in repr(summary)


def test_custom_headers_are_rejected_when_provider_has_websocket_endpoint() -> None:
    config = PROXY_ADAPTER.validate_python(
        {
            "mode": "custom",
            "url": "http://proxy.example:8080",
            "auth": {"type": "headers", "headers": {"X-Proxy-Token": "secret"}},
        }
    )

    with pytest.raises(ValueError, match="WebSocket"):
        validate_proxy_websocket_compatibility(config, ["wss://provider.example/realtime"])


def test_basic_auth_is_compatible_with_websocket_endpoint() -> None:
    config = PROXY_ADAPTER.validate_python(
        {
            "mode": "custom",
            "url": "http://proxy.example:8080",
            "auth": {"type": "basic", "username": "user", "password": "password"},
        }
    )

    validate_proxy_websocket_compatibility(config, ["wss://provider.example/realtime"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("username", "user:name"),
        ("username", "user/name"),
        ("username", "user[name"),
        ("password", "pass?word"),
        ("password", "密碼"),
    ],
)
def test_basic_auth_rejects_credentials_websocket_cannot_represent(
    field: str,
    value: str,
) -> None:
    auth = {"type": "basic", "username": "user", "password": "password"}
    auth[field] = value
    config = PROXY_ADAPTER.validate_python(
        {
            "mode": "custom",
            "url": "http://proxy.example:8080",
            "auth": auth,
        }
    )

    with pytest.raises(ValueError, match="WebSocket"):
        validate_proxy_websocket_compatibility(config, ["wss://provider.example/realtime"])

    validate_proxy_websocket_compatibility(config, [None])
