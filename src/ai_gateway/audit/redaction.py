from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-api-key",
        "x-goog-api-key",
        "cookie",
        "set-cookie",
    }
)

SENSITIVE_JSON_KEYS = frozenset(
    {
        "api_key",
        "access_token",
        "refresh_token",
        "password",
        "proxy",
        "secret",
        "credential",
    }
)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return non-sensitive headers without changing their names or values."""

    return {
        name: value for name, value in headers.items() if name.casefold() not in SENSITIVE_HEADERS
    }


def redact_json(value: Any) -> Any:
    """Recursively redact values selected by case-insensitive credential keys."""

    if isinstance(value, Mapping):
        return {
            str(key): (
                REDACTED if str(key).casefold() in SENSITIVE_JSON_KEYS else redact_json(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_json(item) for item in value]
    return value
