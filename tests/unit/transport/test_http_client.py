from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Coroutine
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from ai_gateway.core.config import Settings
from ai_gateway.transport.http import HttpClientFactory


class FakeAsyncClient:
    created: list[FakeAsyncClient] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.close_calls = 0
        self.created.append(self)

    async def aclose(self) -> None:
        self.close_calls += 1


@pytest.fixture(autouse=True)
def fake_async_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.created = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)


def proxy_settings(
    *,
    http_proxy: str | None = None,
    https_proxy: str | None = None,
    no_proxy: str = "",
) -> Settings:
    return cast(
        Settings,
        SimpleNamespace(
            database_url="mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway",
            http_proxy=http_proxy,
            https_proxy=https_proxy,
            no_proxy=no_proxy,
        ),
    )


@pytest.mark.asyncio
async def test_http_and_https_select_their_configured_long_lived_proxy_clients() -> None:
    factory = HttpClientFactory(
        proxy_settings(
            http_proxy="http://http-proxy.internal:8080",
            https_proxy="http://https-proxy.internal:8443",
        )
    )

    http_client = await factory.client_for("http://provider.example/v1/models")
    https_client = await factory.client_for("https://provider.example/v1/models")

    assert http_client is FakeAsyncClient.created[1]
    assert https_client is FakeAsyncClient.created[2]
    assert await factory.client_for("http://other.example") is http_client
    assert await factory.client_for("https://other.example") is https_client


@pytest.mark.asyncio
async def test_https_falls_back_to_the_http_proxy_client() -> None:
    factory = HttpClientFactory(proxy_settings(http_proxy="http://shared-proxy.internal:8080"))

    http_client = await factory.client_for("http://provider.example")

    assert await factory.client_for("https://provider.example") is http_client
    assert len(FakeAsyncClient.created) == 2


@pytest.mark.asyncio
async def test_no_proxy_host_returns_the_direct_client_without_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_getaddrinfo(*args: object, **kwargs: object) -> object:
        pytest.fail("NO_PROXY exact-host matching must not resolve DNS")

    monkeypatch.setattr(socket, "getaddrinfo", unexpected_getaddrinfo)
    factory = HttpClientFactory(
        proxy_settings(
            http_proxy="http://proxy.internal:8080",
            no_proxy="provider.example,10.0.0.0/8",
        )
    )

    assert await factory.client_for("http://provider.example/v1") is FakeAsyncClient.created[0]


@pytest.mark.asyncio
async def test_hostname_resolving_into_no_proxy_cidr_returns_direct_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_getaddrinfo(
        host: str,
        port: int | None,
        *,
        type: socket.SocketKind,
    ) -> list[tuple[socket.AddressFamily, socket.SocketKind, int, str, tuple[str, int]]]:
        calls.append(host)
        assert port is None
        assert type is socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.23.45.67", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    factory = HttpClientFactory(
        proxy_settings(
            http_proxy="http://proxy.internal:8080",
            no_proxy="10.0.0.0/8",
        )
    )

    assert await factory.client_for("http://provider.example/v1") is FakeAsyncClient.created[0]
    assert calls == ["provider.example"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("network", "resolved_ip", "family"),
    [
        ("10.23.45.67/32", "10.23.45.67", socket.AF_INET),
        ("2001:db8::7/128", "2001:db8::7", socket.AF_INET6),
    ],
)
async def test_hostname_resolving_into_host_prefix_network_returns_direct_client(
    monkeypatch: pytest.MonkeyPatch,
    network: str,
    resolved_ip: str,
    family: socket.AddressFamily,
) -> None:
    calls: list[str] = []

    def fake_getaddrinfo(
        host: str,
        port: int | None,
        *,
        type: socket.SocketKind,
    ) -> list[tuple[socket.AddressFamily, socket.SocketKind, int, str, tuple[str, int]]]:
        calls.append(host)
        assert port is None
        assert type is socket.SOCK_STREAM
        return [(family, socket.SOCK_STREAM, 6, "", (resolved_ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    factory = HttpClientFactory(
        proxy_settings(
            http_proxy="http://proxy.internal:8080",
            no_proxy=network,
        )
    )

    assert await factory.client_for("http://provider.example/v1") is FakeAsyncClient.created[0]
    assert calls == ["provider.example"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("no_proxy", "ip_url"),
    [
        ("10.23.45.67", "http://10.23.45.67/v1"),
        ("2001:db8::7", "http://[2001:db8::7]/v1"),
    ],
)
async def test_plain_ip_no_proxy_rule_does_not_resolve_unrelated_hostname(
    monkeypatch: pytest.MonkeyPatch,
    no_proxy: str,
    ip_url: str,
) -> None:
    def unexpected_getaddrinfo(*args: object, **kwargs: object) -> object:
        pytest.fail("plain IP NO_PROXY entries must not resolve unrelated hostnames")

    monkeypatch.setattr(socket, "getaddrinfo", unexpected_getaddrinfo)
    factory = HttpClientFactory(
        proxy_settings(
            http_proxy="http://proxy.internal:8080",
            no_proxy=no_proxy,
        )
    )

    assert await factory.client_for("http://provider.example/v1") is FakeAsyncClient.created[1]
    assert await factory.client_for(ip_url) is FakeAsyncClient.created[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "no_proxy"),
    [
        ("http://provider.example/v1", "provider.example:80"),
        ("http://provider.example:80/v1", "provider.example:80"),
        ("https://secure.example/v1", "secure.example:443"),
        ("https://secure.example:443/v1", "secure.example:443"),
    ],
)
async def test_no_proxy_default_port_matches_implicit_and_explicit_urls(
    url: str,
    no_proxy: str,
) -> None:
    factory = HttpClientFactory(
        proxy_settings(
            http_proxy="http://http-proxy.internal:8080",
            https_proxy="http://https-proxy.internal:8443",
            no_proxy=no_proxy,
        )
    )

    assert await factory.client_for(url) is FakeAsyncClient.created[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("http_proxy", [None, "http://proxy.internal:8080"])
async def test_hostless_outbound_url_is_rejected_before_client_selection(
    http_proxy: str | None,
) -> None:
    factory = HttpClientFactory(proxy_settings(http_proxy=http_proxy))

    with pytest.raises(ValueError, match="must include a host"):
        await factory.client_for("http:///v1/models")


@pytest.mark.asyncio
async def test_dns_failure_is_not_treated_as_no_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_getaddrinfo(*args: object, **kwargs: object) -> object:
        raise socket.gaierror("unresolvable in test")

    monkeypatch.setattr(socket, "getaddrinfo", failing_getaddrinfo)
    factory = HttpClientFactory(
        proxy_settings(
            http_proxy="http://proxy.internal:8080",
            no_proxy="10.0.0.0/8",
        )
    )

    assert await factory.client_for("http://provider.example/v1") is FakeAsyncClient.created[1]


@pytest.mark.asyncio
async def test_dns_resolution_has_a_two_second_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(*args: object, **kwargs: object) -> object:
        pytest.fail("the timeout shim should consume the coroutine first")

    async def timeout(
        awaitable: Coroutine[Any, Any, object],
        timeout: float | None,
    ) -> object:
        assert timeout == 2.0
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(asyncio, "wait_for", timeout)
    factory = HttpClientFactory(
        proxy_settings(
            http_proxy="http://proxy.internal:8080",
            no_proxy="10.0.0.0/8",
        )
    )

    assert await factory.client_for("http://provider.example/v1") is FakeAsyncClient.created[1]


def test_clients_enable_http2_pooling_and_required_timeouts() -> None:
    HttpClientFactory(
        proxy_settings(
            http_proxy="http://http-proxy.internal:8080",
            https_proxy="http://https-proxy.internal:8443",
        )
    )

    assert len(FakeAsyncClient.created) == 3
    for client in FakeAsyncClient.created:
        assert client.kwargs["http2"] is True
        assert client.kwargs["trust_env"] is False
        assert isinstance(client.kwargs["limits"], httpx.Limits)
        timeout = client.kwargs["timeout"]
        assert timeout.connect == 10.0
        assert timeout.read == 300.0
        assert timeout.write == 300.0
        assert timeout.pool == 10.0


@pytest.mark.asyncio
async def test_factory_closes_each_client_exactly_once() -> None:
    factory = HttpClientFactory(
        proxy_settings(
            http_proxy="http://http-proxy.internal:8080",
            https_proxy="http://https-proxy.internal:8443",
        )
    )

    await factory.aclose()
    await factory.aclose()

    assert [client.close_calls for client in FakeAsyncClient.created] == [1, 1, 1]


def test_proxy_credentials_are_redacted_from_logs_and_repr(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="ai_gateway.transport.http")

    factory = HttpClientFactory(
        proxy_settings(http_proxy="http://proxy-user:proxy-password@proxy.internal:8080")
    )

    log_output = caplog.text
    representation = repr(factory)
    assert "proxy.internal:8080" in log_output
    assert "proxy.internal:8080" in representation
    assert "proxy-user" not in log_output
    assert "proxy-password" not in log_output
    assert "proxy-user" not in representation
    assert "proxy-password" not in representation


def test_proxy_credentials_are_redacted_from_settings_repr() -> None:
    settings = Settings(
        _env_file=None,
        jwt_secret="test-jwt-secret",
        encryption_key="test-encryption-key",
        http_proxy="http://proxy-user:proxy-password@proxy.internal:8080",
    )

    representation = repr(settings)
    assert "proxy-user" not in representation
    assert "proxy-password" not in representation


def test_proxy_credentials_are_redacted_from_configuration_errors() -> None:
    with pytest.raises(ValueError) as caught:
        HttpClientFactory(proxy_settings(http_proxy="://proxy-user:proxy-password@proxy.internal"))

    message = str(caught.value)
    assert FakeAsyncClient.created == []
    assert "proxy-user" not in message
    assert "proxy-password" not in message


@pytest.mark.asyncio
async def test_fastapi_lifespan_publishes_and_closes_the_factory_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_gateway import main

    factories: list[StubHttpClientFactory] = []
    schedulers: list[StubModelSyncScheduler] = []

    class StubHttpClientFactory:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings
            self.close_calls = 0
            factories.append(self)

        async def aclose(self) -> None:
            self.close_calls += 1

    class StubModelSyncScheduler:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.started = asyncio.Event()
            self.stopped = asyncio.Event()
            self.stop_calls = 0
            self.completed = False
            schedulers.append(self)

        async def run(self) -> None:
            self.started.set()
            await self.stopped.wait()
            self.completed = True

        def stop(self) -> None:
            self.stop_calls += 1
            self.stopped.set()

    monkeypatch.setattr(main, "HttpClientFactory", StubHttpClientFactory)
    monkeypatch.setattr(main, "ModelSyncScheduler", StubModelSyncScheduler)
    settings = proxy_settings()
    app = main.create_app(settings=settings)

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(schedulers[0].started.wait(), timeout=1)
        assert app.state.http_client_factory is factories[0]
        assert app.state.model_sync_scheduler is schedulers[0]
        assert factories[0].settings is settings
        assert factories[0].close_calls == 0

    assert factories[0].close_calls == 1
    assert schedulers[0].stop_calls == 1
    assert schedulers[0].completed is True
