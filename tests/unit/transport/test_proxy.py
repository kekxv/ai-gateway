import socket

import pytest

from ai_gateway.transport.proxy import NoProxyMatcher


@pytest.mark.parametrize(
    ("value", "host", "expected"),
    [
        ("api.example.com", "api.example.com", True),
        ("api.example.com", "API.EXAMPLE.COM", True),
        ("api.example.com", "other.example.com", False),
        (".example.com", "api.example.com", True),
        (".example.com", "example.com", True),
        (".example.com", "notexample.com", False),
        ("internal.example:8443", "internal.example:8443", True),
        ("internal.example:8443", "internal.example:443", False),
        ("internal.example:8443", "internal.example", False),
        ("127.0.0.1", "127.0.0.1", True),
        ("127.0.0.1", "127.0.0.2", False),
        ("2001:db8::1", "2001:db8::1", True),
        ("2001:db8::1", "[2001:db8::1]:443", True),
        ("10.0.0.0/8", "10.12.34.56", True),
        ("10.0.0.0/8", "192.0.2.1", False),
        ("2001:db8::/32", "2001:db8:1::7", True),
        ("2001:db8::/32", "2001:db9::1", False),
        ("*", "anything.example", True),
        (" localhost,  .example.org , 10.0.0.0/8 ", "api.example.org", True),
    ],
)
def test_no_proxy_matches_hosts_addresses_and_networks(
    value: str,
    host: str,
    expected: bool,
) -> None:
    matcher = NoProxyMatcher.from_string(value)

    assert matcher.matches(host, ()) is expected


def test_hostname_matches_an_excluded_ipv4_cidr_through_resolved_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(
        host: str,
        port: int | None,
        *,
        type: socket.SocketKind,
    ) -> list[tuple[socket.AddressFamily, socket.SocketKind, int, str, tuple[str, int]]]:
        assert host == "service.internal"
        assert port is None
        assert type is socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.23.45.67", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    results = socket.getaddrinfo("service.internal", None, type=socket.SOCK_STREAM)
    resolved_ips = [result[4][0] for result in results]

    matcher = NoProxyMatcher.from_string("10.0.0.0/8")

    assert matcher.matches("service.internal", resolved_ips)


def test_hostname_matches_an_excluded_ipv6_cidr_through_resolved_addresses() -> None:
    matcher = NoProxyMatcher.from_string("2001:db8::/32")

    assert matcher.matches("service.internal", ["2001:db8:2::9"])


def test_non_ip_resolution_results_are_ignored() -> None:
    matcher = NoProxyMatcher.from_string("10.0.0.0/8")

    assert not matcher.matches("service.internal", ["not-an-address", "192.0.2.4"])


@pytest.mark.parametrize("value", ["10.23.45.67/32", "2001:db8::7/128"])
def test_host_prefix_network_rules_still_require_hostname_resolution(value: str) -> None:
    matcher = NoProxyMatcher.from_string(value)

    assert matcher.needs_dns_resolution


@pytest.mark.parametrize("value", ["10.23.45.67", "2001:db8::7"])
def test_plain_ip_rules_do_not_require_hostname_resolution(value: str) -> None:
    matcher = NoProxyMatcher.from_string(value)

    assert not matcher.needs_dns_resolution
