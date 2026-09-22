"""Upstream balance queries for provider accounts.

Each supported upstream exposes its remaining credit through a different
endpoint and payload shape. This module keeps the type-specific knowledge in
one place so that the admin API, the scheduler and the auto-detection flow all
share the same parsing rules.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any
from typing import Protocol as TypingProtocol

import httpx
import orjson

from ai_gateway.catalog.credentials import ProviderCredential
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import BalanceQueryType, Protocol
from ai_gateway.core.security import decrypt_secret

DEFAULT_NEW_API_QUOTA_PER_UNIT = Decimal("500000")
DEFAULT_BALANCE_CURRENCY = "USD"
DEFAULT_CUSTOM_METHOD = "GET"
MAX_BALANCE_ERROR_CHARS = 1024
_BALANCE_QUANTUM = Decimal("0.00000001")
_SUPPORTED_CUSTOM_METHODS = ("GET", "POST")
_BASE_URL_SUFFIXES = ("/v1", "/v1beta")
_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_DISALLOWED_BALANCE_HEADERS = frozenset(
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
_PATH_TOKEN = re.compile(r"^([^\[\]]*)((?:\[\d+\])*)$")


class BalanceQueryError(RuntimeError):
    """The upstream balance could not be read."""


class BalanceConfigError(ValueError):
    """Stored or submitted balance configuration is invalid."""


class AsyncHttpClient(TypingProtocol):
    async def send(self, request: httpx.Request) -> httpx.Response: ...


@dataclass(frozen=True, slots=True)
class BalanceQueryConfig:
    """Optional per-provider overrides for the balance endpoint."""

    base_url: str | None = None
    api_key: str | None = None
    user_id: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    path: str | None = None
    method: str = DEFAULT_CUSTOM_METHOD
    amount_path: str | None = None
    used_path: str | None = None
    available_path: str | None = None
    currency: str | None = None
    divisor: Decimal | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> BalanceQueryConfig:
        for key in values:
            if key not in _CONFIG_FIELDS:
                raise BalanceConfigError(f"Unknown balance configuration field: {key}")
        return cls(
            base_url=_optional_text(values, "base_url", max_length=512),
            api_key=_optional_text(values, "api_key", max_length=2048),
            user_id=_optional_text(values, "user_id", max_length=128),
            headers=_headers(values.get("headers")),
            path=_optional_text(values, "path", max_length=1024),
            method=_method(values.get("method")),
            amount_path=_optional_text(values, "amount_path", max_length=512),
            used_path=_optional_text(values, "used_path", max_length=512),
            available_path=_optional_text(values, "available_path", max_length=512),
            currency=_optional_text(values, "currency", max_length=16),
            divisor=_optional_decimal(values.get("divisor")),
        )

    def to_mapping(self) -> dict[str, object]:
        mapping: dict[str, object] = {}
        for name, value in (
            ("base_url", self.base_url),
            ("api_key", self.api_key),
            ("user_id", self.user_id),
            ("path", self.path),
            ("amount_path", self.amount_path),
            ("used_path", self.used_path),
            ("available_path", self.available_path),
            ("currency", self.currency),
        ):
            if value is not None:
                mapping[name] = value
        if self.headers:
            mapping["headers"] = dict(self.headers)
        if self.method != DEFAULT_CUSTOM_METHOD:
            mapping["method"] = self.method
        if self.divisor is not None:
            mapping["divisor"] = str(self.divisor)
        return mapping


_CONFIG_FIELDS = frozenset(
    {
        "base_url",
        "api_key",
        "user_id",
        "headers",
        "path",
        "method",
        "amount_path",
        "used_path",
        "available_path",
        "currency",
        "divisor",
    }
)


@dataclass(frozen=True, slots=True)
class BalanceProbe:
    """Provider-side inputs shared by every candidate upstream type."""

    base_url: str
    credential_encrypted: bytes
    protocol: Protocol
    config: BalanceQueryConfig
    extra_headers_encrypted: bytes | None = None


@dataclass(frozen=True, slots=True)
class BalanceResult:
    query_type: BalanceQueryType
    amount: Decimal
    currency: str
    used: Decimal | None = None
    is_available: bool | None = None


def validate_balance_config(
    query_type: BalanceQueryType,
    config: BalanceQueryConfig,
) -> None:
    """Reject configurations that cannot produce a balance."""

    if config.divisor is not None and config.divisor <= 0:
        raise BalanceConfigError("Balance divisor must be greater than zero")
    if config.method not in _SUPPORTED_CUSTOM_METHODS:
        raise BalanceConfigError("Unsupported balance query method")
    if query_type is BalanceQueryType.CUSTOM:
        if not config.path:
            raise BalanceConfigError("Custom balance queries require a request path")
        if not config.amount_path:
            raise BalanceConfigError("Custom balance queries require an amount JSON path")


def balance_url(
    base_url: str,
    query_type: BalanceQueryType,
    config: BalanceQueryConfig,
) -> str:
    base = (config.base_url or base_url).strip().rstrip("/")
    if not base:
        raise BalanceConfigError("Provider base URL is required for balance queries")
    if query_type is BalanceQueryType.CUSTOM:
        path = (config.path or "").strip()
        if not path:
            raise BalanceConfigError("Custom balance queries require a request path")
        if path.startswith(("http://", "https://")):
            return path
        return f"{base}/{path.lstrip('/')}"
    if query_type is BalanceQueryType.NEW_API:
        return f"{_host_root(base)}/api/user/self"
    if query_type is BalanceQueryType.DEEPSEEK:
        return f"{_host_root(base)}/user/balance"
    if query_type is BalanceQueryType.OPENROUTER:
        if base.endswith("/api/v1"):
            return f"{base}/credits"
        if base.endswith("/v1"):
            return f"{base[: -len('/v1')].rstrip('/')}/api/v1/credits"
        return f"{base}/api/v1/credits"
    raise BalanceConfigError("Unsupported balance query type")


async def query_balance(
    probe: BalanceProbe,
    query_type: BalanceQueryType,
    *,
    client: AsyncHttpClient,
    settings: Settings,
) -> BalanceResult:
    validate_balance_config(query_type, probe.config)
    url = balance_url(probe.base_url, query_type, probe.config)
    request = httpx.Request(
        probe.config.method if query_type is BalanceQueryType.CUSTOM else "GET",
        url,
        headers=_request_headers(probe, query_type, settings),
    )
    response = await client.send(request)
    response.raise_for_status()
    return parse_balance_response(query_type, probe.config, _json_object(response))


async def detect_balance_types(
    probe: BalanceProbe,
    *,
    client: AsyncHttpClient,
    settings: Settings,
    candidates: Sequence[BalanceQueryType] | None = None,
) -> list[BalanceResult]:
    """Probe every built-in upstream type and return the ones that answered."""

    resolved: list[BalanceResult] = []
    for query_type in _detection_order(probe, candidates):
        try:
            resolved.append(
                await query_balance(probe, query_type, client=client, settings=settings)
            )
        except (httpx.HTTPError, BalanceQueryError, BalanceConfigError, ValueError):
            continue
    return resolved


def _detection_order(
    probe: BalanceProbe,
    candidates: Sequence[BalanceQueryType] | None,
) -> list[BalanceQueryType]:
    available = [
        BalanceQueryType.NEW_API,
        BalanceQueryType.DEEPSEEK,
        BalanceQueryType.OPENROUTER,
    ]
    if candidates is not None:
        available = [item for item in available if item in candidates]
    try:
        host = httpx.URL(probe.config.base_url or probe.base_url).host.lower()
    except (httpx.InvalidURL, ValueError):
        return available
    if "openrouter" in host:
        available.sort(key=lambda item: item is not BalanceQueryType.OPENROUTER)
    elif "deepseek" in host:
        available.sort(key=lambda item: item is not BalanceQueryType.DEEPSEEK)
    return available


def parse_balance_response(
    query_type: BalanceQueryType,
    config: BalanceQueryConfig,
    payload: Mapping[str, Any],
) -> BalanceResult:
    if query_type is BalanceQueryType.NEW_API:
        return _parse_new_api(config, payload)
    if query_type is BalanceQueryType.DEEPSEEK:
        return _parse_deepseek(config, payload)
    if query_type is BalanceQueryType.OPENROUTER:
        return _parse_openrouter(config, payload)
    if query_type is BalanceQueryType.CUSTOM:
        return _parse_custom(config, payload)
    raise BalanceConfigError("Unsupported balance query type")


def extract_json_path(payload: object, path: str) -> Any:
    """Resolve a dotted path such as ``data.balance_infos[0].total_balance``."""

    if not path.strip():
        raise BalanceQueryError("Balance JSON path is empty")
    current: Any = payload
    for raw_token in path.strip().split("."):
        match = _PATH_TOKEN.match(raw_token.strip())
        if match is None:
            raise BalanceQueryError(f"Invalid balance JSON path: {path}")
        name, indexes = match.groups()
        if name:
            if not isinstance(current, Mapping) or name not in current:
                raise BalanceQueryError(f"Balance JSON path not found: {path}")
            current = current[name]
        for index in re.findall(r"\[(\d+)\]", indexes):
            if not isinstance(current, Sequence) or isinstance(current, (str, bytes)):
                raise BalanceQueryError(f"Balance JSON path is not a list: {path}")
            position = int(index)
            if position >= len(current):
                raise BalanceQueryError(f"Balance JSON path index is out of range: {path}")
            current = current[position]
    return current


def truncate_balance_error(message: str) -> str:
    if len(message) <= MAX_BALANCE_ERROR_CHARS:
        return message
    return f"{message[: MAX_BALANCE_ERROR_CHARS - 1]}…"


def _parse_new_api(config: BalanceQueryConfig, payload: Mapping[str, Any]) -> BalanceResult:
    if payload.get("success") is False:
        raise BalanceQueryError(_upstream_message(payload) or "Upstream reported a failure")
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise BalanceQueryError("Upstream response is missing the user payload")
    quota = _as_decimal(data.get("quota"), field_name="quota")
    divisor = config.divisor or DEFAULT_NEW_API_QUOTA_PER_UNIT
    used_raw = data.get("used_quota")
    return BalanceResult(
        query_type=BalanceQueryType.NEW_API,
        amount=_quantize(quota / divisor),
        currency=config.currency or DEFAULT_BALANCE_CURRENCY,
        used=(
            _quantize(_as_decimal(used_raw, field_name="used_quota") / divisor)
            if used_raw is not None
            else None
        ),
    )


def _parse_deepseek(config: BalanceQueryConfig, payload: Mapping[str, Any]) -> BalanceResult:
    available = payload.get("is_available")
    infos = payload.get("balance_infos")
    if not isinstance(infos, list) or not infos:
        raise BalanceQueryError("Upstream response is missing balance information")
    entry: Mapping[str, Any] | None = None
    for raw_entry in infos:
        if not isinstance(raw_entry, Mapping):
            continue
        if config.currency and raw_entry.get("currency") != config.currency:
            continue
        entry = raw_entry
        break
    if entry is None:
        raise BalanceQueryError("Upstream response has no balance for the requested currency")
    currency = entry.get("currency")
    return BalanceResult(
        query_type=BalanceQueryType.DEEPSEEK,
        amount=_quantize(_as_decimal(entry.get("total_balance"), field_name="total_balance")),
        currency=(
            config.currency
            or (currency if isinstance(currency, str) and currency else DEFAULT_BALANCE_CURRENCY)
        ),
        is_available=available if isinstance(available, bool) else None,
    )


def _parse_openrouter(config: BalanceQueryConfig, payload: Mapping[str, Any]) -> BalanceResult:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise BalanceQueryError("Upstream response is missing the credits payload")
    total = _as_decimal(data.get("total_credits"), field_name="total_credits")
    used_raw = data.get("total_usage")
    used = _as_decimal(used_raw, field_name="total_usage") if used_raw is not None else Decimal(0)
    return BalanceResult(
        query_type=BalanceQueryType.OPENROUTER,
        amount=_quantize(total - used),
        currency=config.currency or DEFAULT_BALANCE_CURRENCY,
        used=_quantize(used),
    )


def _parse_custom(config: BalanceQueryConfig, payload: Mapping[str, Any]) -> BalanceResult:
    raw_amount = extract_json_path(payload, config.amount_path or "")
    divisor = config.divisor or Decimal(1)
    available = extract_json_path(payload, config.available_path) if config.available_path else None
    used = extract_json_path(payload, config.used_path) if config.used_path else None
    return BalanceResult(
        query_type=BalanceQueryType.CUSTOM,
        amount=_quantize(_as_decimal(raw_amount, field_name="balance") / divisor),
        currency=config.currency or DEFAULT_BALANCE_CURRENCY,
        used=_quantize(_as_decimal(used, field_name="used balance") / divisor)
        if used is not None
        else None,
        is_available=available if isinstance(available, bool) else None,
    )


def _request_headers(
    probe: BalanceProbe,
    query_type: BalanceQueryType,
    settings: Settings,
) -> httpx.Headers:
    credential = _credential(probe, settings)
    headers = httpx.Headers(credential.auth_headers(probe.protocol))
    if probe.extra_headers_encrypted is not None:
        headers.update(_decrypt_headers(probe.extra_headers_encrypted, settings))
    if query_type is BalanceQueryType.NEW_API and probe.config.user_id:
        headers["New-Api-User"] = probe.config.user_id
    headers.update(dict(probe.config.headers))
    return headers


def _credential(probe: BalanceProbe, settings: Settings) -> ProviderCredential:
    values = _decrypt_object(probe.credential_encrypted, settings)
    credential = ProviderCredential.from_mapping(values)
    if not probe.config.api_key:
        return credential
    return replace(
        credential,
        api_key=probe.config.api_key,
        auth_scheme=None if credential.auth_scheme == "none" else credential.auth_scheme,
    )


def _decrypt_object(encrypted: bytes, settings: Settings) -> dict[str, object]:
    try:
        value = orjson.loads(decrypt_secret(encrypted, settings=settings))
    except Exception:
        raise BalanceQueryError("Provider credential could not be decoded") from None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise BalanceQueryError("Provider credential must be a JSON object")
    return value


def _decrypt_headers(encrypted: bytes, settings: Settings) -> dict[str, str]:
    values = _decrypt_object(encrypted, settings)
    if not all(isinstance(name, str) and isinstance(value, str) for name, value in values.items()):
        raise BalanceQueryError("Provider headers must be a JSON object of string values")
    return {name: value for name, value in values.items() if isinstance(value, str)}


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError:
        raise BalanceQueryError("Upstream balance response is not valid JSON") from None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise BalanceQueryError("Upstream balance response must be a JSON object")
    return value


def _host_root(base_url: str) -> str:
    for suffix in _BASE_URL_SUFFIXES:
        if base_url.endswith(suffix):
            return base_url[: -len(suffix)].rstrip("/")
    return base_url


def _as_decimal(value: object, *, field_name: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise BalanceQueryError(f"Upstream response has no numeric {field_name}")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            raise BalanceQueryError(f"Upstream response has a non-numeric {field_name}") from None
    raise BalanceQueryError(f"Upstream response has a non-numeric {field_name}")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_BALANCE_QUANTUM)


def _upstream_message(payload: Mapping[str, Any]) -> str:
    message = payload.get("message") or payload.get("error")
    return message if isinstance(message, str) else ""


def _optional_text(
    values: Mapping[str, object],
    name: str,
    *,
    max_length: int,
) -> str | None:
    if name not in values or values[name] is None:
        return None
    value = values[name]
    if not isinstance(value, str) or not value.strip():
        raise BalanceConfigError(f"Balance configuration field {name} must be a non-empty string")
    if len(value) > max_length:
        raise BalanceConfigError(f"Balance configuration field {name} is too long")
    return value.strip()


def _method(value: object) -> str:
    if value is None:
        return DEFAULT_CUSTOM_METHOD
    if not isinstance(value, str) or value.upper() not in _SUPPORTED_CUSTOM_METHODS:
        raise BalanceConfigError("Unsupported balance query method")
    return value.upper()


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise BalanceConfigError("Balance divisor must be a number")
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            raise BalanceConfigError("Balance divisor must be a number") from None
    raise BalanceConfigError("Balance divisor must be a number")


def _headers(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise BalanceConfigError("Balance headers must be a JSON object")
    headers: dict[str, str] = {}
    for name, header_value in value.items():
        if not isinstance(name, str) or _HEADER_NAME.fullmatch(name) is None:
            raise BalanceConfigError("Balance headers contain an invalid name")
        if name.casefold() in _DISALLOWED_BALANCE_HEADERS:
            raise BalanceConfigError(f"Balance header {name} cannot be overridden")
        if (
            not isinstance(header_value, str)
            or not header_value
            or any(ord(character) < 0x20 or ord(character) > 0x7E for character in header_value)
        ):
            raise BalanceConfigError(f"Balance header {name} has an invalid value")
        headers[name] = header_value
    return headers
