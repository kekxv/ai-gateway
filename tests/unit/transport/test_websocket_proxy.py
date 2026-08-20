from __future__ import annotations

import pytest
from websockets.asyncio.client import parse_proxy

from ai_gateway.core.config import Settings
from ai_gateway.transport.provider_proxy import (
    ProviderProxyBasicAuth,
    ProviderProxyCustom,
    ProviderProxyDirect,
    ProviderProxyHeaderAuth,
    encrypt_provider_proxy,
)
from ai_gateway.transport.websocket import websocket_proxy_for


def settings(*, https_proxy: str | None = None) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret="websocket-proxy-test-jwt-secret",
        encryption_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        https_proxy=https_proxy,
        no_proxy="",
    )


@pytest.mark.asyncio
async def test_provider_basic_proxy_overrides_global_websocket_proxy() -> None:
    active_settings = settings(https_proxy="http://global-proxy.internal:8080")
    encrypted = encrypt_provider_proxy(
        ProviderProxyCustom(
            mode="custom",
            url="https://provider-proxy.internal:8443",
            auth=ProviderProxyBasicAuth(type="basic", username="proxy user", password="p@ss:word"),
        ),
        settings=active_settings,
    )

    proxy = await websocket_proxy_for(
        "wss://provider.example/realtime",
        active_settings,
        proxy_config_encrypted=encrypted,
    )

    assert proxy is not None
    parsed = parse_proxy(proxy)
    assert parsed.username == "proxy user"
    assert parsed.password == "p@ss:word"


@pytest.mark.asyncio
async def test_provider_direct_bypasses_global_websocket_proxy() -> None:
    active_settings = settings(https_proxy="http://global-proxy.internal:8080")
    encrypted = encrypt_provider_proxy(ProviderProxyDirect(mode="direct"), settings=active_settings)

    assert (
        await websocket_proxy_for(
            "wss://provider.example/realtime",
            active_settings,
            proxy_config_encrypted=encrypted,
        )
        is None
    )


@pytest.mark.asyncio
async def test_custom_proxy_headers_fail_closed_for_websocket() -> None:
    active_settings = settings()
    encrypted = encrypt_provider_proxy(
        ProviderProxyCustom(
            mode="custom",
            url="http://provider-proxy.internal:8080",
            auth=ProviderProxyHeaderAuth(type="headers", headers={"X-Proxy-Token": "secret"}),
        ),
        settings=active_settings,
    )

    with pytest.raises(ValueError, match="custom authentication headers"):
        await websocket_proxy_for(
            "wss://provider.example/realtime",
            active_settings,
            proxy_config_encrypted=encrypted,
        )
