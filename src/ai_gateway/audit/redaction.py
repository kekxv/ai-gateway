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

# Normalize case, underscores, and hyphens before matching. Keep this set
# limited to complete credential field names so ordinary text and token counts
# remain visible.
_NORMALIZED_SENSITIVE_JSON_KEYS = frozenset(
    key.casefold().replace("_", "").replace("-", "") for key in SENSITIVE_JSON_KEYS
) | frozenset(
    {
        "apikey",
        "accesstoken",
        "refreshtoken",
        "clientsecret",
        "authtoken",
        "privatekey",
        "credentials",
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
                REDACTED
                if _normalize_json_key(key) in _NORMALIZED_SENSITIVE_JSON_KEYS
                else redact_json(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_json(item) for item in value]
    return value


def _normalize_json_key(key: object) -> str:
    return str(key).casefold().replace("_", "").replace("-", "")
