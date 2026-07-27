from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from ai_gateway.core.enums import Protocol

AuthScheme = Literal["Bearer", "ApiKey", "none"]

_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_DISALLOWED_AUTH_HEADERS = frozenset(
    {
        "connection",
        "content-length",
        "cookie",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderCredential:
    api_key: str | None
    auth_scheme: AuthScheme | None
    auth_header: str | None
    anthropic_version: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> ProviderCredential:
        api_key = _optional_header_value(values, "api_key")

        raw_scheme = values.get("auth_scheme")
        if raw_scheme is None:
            auth_scheme: AuthScheme | None = None
        elif raw_scheme == "Bearer":
            auth_scheme = "Bearer"
        elif raw_scheme == "ApiKey":
            auth_scheme = "ApiKey"
        elif raw_scheme == "none":
            auth_scheme = "none"
        else:
            raise ValueError("Provider credential contains an invalid auth_scheme")

        raw_header = values.get("auth_header")
        if raw_header is not None:
            if (
                not isinstance(raw_header, str)
                or len(raw_header) > 128
                or _HEADER_NAME.fullmatch(raw_header) is None
                or raw_header.casefold() in _DISALLOWED_AUTH_HEADERS
            ):
                raise ValueError("Provider credential contains an invalid auth_header")
        auth_header = raw_header

        anthropic_version = _optional_header_value(values, "anthropic_version")
        return cls(
            api_key=api_key,
            auth_scheme=auth_scheme,
            auth_header=auth_header,
            anthropic_version=anthropic_version or "2023-06-01",
        )

    def auth_headers(self, protocol: Protocol) -> dict[str, str]:
        defaults = {
            Protocol.OPENAI: ("authorization", "Bearer"),
            Protocol.CLAUDE: ("x-api-key", "ApiKey"),
            Protocol.GEMINI: ("x-goog-api-key", "ApiKey"),
        }
        try:
            default_header, default_scheme = defaults[protocol]
        except KeyError:
            raise ValueError("Unsupported provider protocol") from None

        headers = (
            {"anthropic-version": self.anthropic_version} if protocol is Protocol.CLAUDE else {}
        )
        if self.api_key is None or self.auth_scheme == "none":
            return headers

        scheme = self.auth_scheme or default_scheme
        value = f"Bearer {self.api_key}" if scheme == "Bearer" else self.api_key
        headers[self.auth_header or default_header] = value
        return headers


def validate_provider_credential(values: dict[str, object]) -> dict[str, object]:
    ProviderCredential.from_mapping(values)
    return values


def _optional_header_value(values: Mapping[str, object], name: str) -> str | None:
    if name not in values:
        return None
    value = values[name]
    if (
        not isinstance(value, str)
        or not value
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value)
    ):
        raise ValueError(f"Provider credential contains an invalid {name}")
    return value
