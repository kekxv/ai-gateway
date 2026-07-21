from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass(frozen=True, slots=True)
class _HostRule:
    host: str
    port: int | None
    is_suffix: bool

    def matches(self, host: str, port: int | None) -> bool:
        if self.port is not None and self.port != port:
            return False
        if self.is_suffix:
            return host == self.host or host.endswith(f".{self.host}")
        return host == self.host


@dataclass(frozen=True, slots=True)
class _NetworkRule:
    network: IPNetwork
    port: int | None
    is_explicit_cidr: bool

    def matches(self, address: IPAddress, port: int | None) -> bool:
        return (self.port is None or self.port == port) and address in self.network


@dataclass(frozen=True, slots=True)
class NoProxyMatcher:
    """A parsed, reusable matcher for a comma-separated ``NO_PROXY`` value."""

    _host_rules: tuple[_HostRule, ...]
    _network_rules: tuple[_NetworkRule, ...]
    _match_all: bool = False

    @classmethod
    def from_string(cls, value: str | None) -> NoProxyMatcher:
        host_rules: list[_HostRule] = []
        network_rules: list[_NetworkRule] = []
        match_all = False

        for raw_entry in (value or "").split(","):
            entry = raw_entry.strip()
            if not entry:
                continue
            if entry == "*":
                match_all = True
                continue

            is_suffix = entry.startswith(".")
            if is_suffix:
                entry = entry[1:]
            host, port = _split_host_and_port(entry)
            normalized_host = _normalize_hostname(host)
            if not normalized_host:
                continue

            try:
                network = ipaddress.ip_network(normalized_host, strict=False)
            except ValueError:
                host_rules.append(_HostRule(host=normalized_host, port=port, is_suffix=is_suffix))
            else:
                network_rules.append(
                    _NetworkRule(
                        network=network,
                        port=port,
                        is_explicit_cidr="/" in normalized_host,
                    )
                )

        return cls(
            _host_rules=tuple(host_rules),
            _network_rules=tuple(network_rules),
            _match_all=match_all,
        )

    @property
    def needs_dns_resolution(self) -> bool:
        """Whether a hostname may match only after resolving a CIDR rule."""

        return any(rule.is_explicit_cidr for rule in self._network_rules)

    def matches(self, host: str, resolved_ips: Iterable[str | IPAddress]) -> bool:
        normalized_host, port = _normalized_host_and_port(host)
        if not normalized_host:
            return False
        if self._match_all:
            return True
        if any(rule.matches(normalized_host, port) for rule in self._host_rules):
            return True

        direct_address = _parse_address(normalized_host)
        if direct_address is not None and any(
            rule.matches(direct_address, port) for rule in self._network_rules
        ):
            return True

        for raw_address in resolved_ips:
            address = _parse_address(raw_address)
            if address is not None and any(
                rule.matches(address, port) for rule in self._network_rules
            ):
                return True
        return False


def _normalized_host_and_port(value: str) -> tuple[str, int | None]:
    host, port = _split_host_and_port(value.strip())
    return _normalize_hostname(host), port


def _split_host_and_port(value: str) -> tuple[str, int | None]:
    if value.startswith("["):
        closing_bracket = value.find("]")
        if closing_bracket != -1:
            host = value[1:closing_bracket]
            remainder = value[closing_bracket + 1 :]
            if remainder.startswith(":") and remainder[1:].isdigit():
                return host, int(remainder[1:])
            return host, None

    if value.count(":") == 1:
        host, separator, raw_port = value.rpartition(":")
        if separator and raw_port.isdigit():
            return host, int(raw_port)
    return value, None


def _normalize_hostname(value: str) -> str:
    return value.rstrip(".").lower()


def _parse_address(value: str | IPAddress) -> IPAddress | None:
    if isinstance(value, ipaddress.IPv4Address | ipaddress.IPv6Address):
        return value
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None
