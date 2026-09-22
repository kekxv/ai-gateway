"""Upstream model price discovery for new-api / one-api style providers.

new-api exposes its ratio configuration over HTTP, both as a public pricing list
(``GET /api/pricing``) and, for administrators, as a ratio map
(``GET /api/ratio_config``). Both describe prices in *ratio units* rather than in
currency: one ratio unit equals two US dollars per million tokens, which is why
the price of a model is derived from its ratio instead of read directly.

This module keeps the upstream-specific knowledge in one place: fetching the
payload, understanding its two shapes, resolving the group ratio that applies and
converting ratios into per-million-token prices. Database writes live in
``ai_gateway.admin.provider_pricing``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from typing import Protocol as TypingProtocol

import httpx

from ai_gateway.catalog.balance import truncate_balance_error
from ai_gateway.catalog.credentials import ProviderCredential
from ai_gateway.core.enums import Protocol

DEFAULT_PRICE_GROUP = "default"
MAX_PRICE_ERROR_CHARS = 1024

#: One new-api ratio unit is worth 500000 quota per dollar, i.e. two dollars per million tokens.
RATIO_PRICE_FACTOR = Decimal("2")
_PRICE_QUANTUM = Decimal("0.00000001")
_RATIO_LIMIT = Decimal("1000000")
_BASE_URL_SUFFIXES = ("/v1", "/v1beta")
_SELF_PATH = "/api/user/self"
_PRICING_PATH = "/api/pricing"


class ModelPriceError(RuntimeError):
    """The upstream price list could not be read."""


class AsyncHttpClient(TypingProtocol):
    async def send(self, request: httpx.Request) -> httpx.Response: ...


@dataclass(frozen=True, slots=True)
class UpstreamModelPrice:
    """One upstream model and the prices derived from its ratios."""

    model_name: str
    quota_type: int
    model_ratio: Decimal | None = None
    completion_ratio: Decimal | None = None
    fixed_price: Decimal | None = None
    input_price_per_million: Decimal | None = None
    output_price_per_million: Decimal | None = None

    @property
    def is_token_priced(self) -> bool:
        return self.input_price_per_million is not None


@dataclass(frozen=True, slots=True)
class UpstreamPricing:
    """The upstream ratio configuration together with the resolved group."""

    group: str
    group_ratio: Decimal
    group_ratios: Mapping[str, Decimal]
    models: Mapping[str, UpstreamModelPrice]


def pricing_url(base_url: str) -> str:
    return f"{_host_root(base_url)}{_PRICING_PATH}"


def self_url(base_url: str) -> str:
    return f"{_host_root(base_url)}{_SELF_PATH}"


async def fetch_upstream_pricing(
    *,
    base_url: str,
    credential: ProviderCredential,
    protocol: Protocol,
    client: AsyncHttpClient,
    group_credential: ProviderCredential | None = None,
    user_id: str | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> UpstreamPricing:
    """Read the upstream price list and resolve the group ratio that applies to us."""

    url = pricing_url(base_url)
    response = await client.send(
        httpx.Request("GET", url, headers=_request_headers(credential, protocol, extra_headers))
    )
    if (
        response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN)
        and group_credential is not None
        and group_credential != credential
    ):
        # Some deployments only serve the price list to an authenticated console token.
        response = await client.send(
            httpx.Request(
                "GET", url, headers=_request_headers(group_credential, protocol, extra_headers)
            )
        )
    if response.status_code == httpx.codes.NOT_FOUND:
        raise ModelPriceError(
            "Upstream has no /api/pricing endpoint, so it does not expose new-api style prices"
        )
    response.raise_for_status()
    payload = _json_object(response, source="pricing")
    group_ratios = parse_group_ratios(payload)

    group = await _resolve_group(
        base_url=base_url,
        credential=group_credential if group_credential is not None else credential,
        protocol=protocol,
        client=client,
        user_id=user_id,
        extra_headers=extra_headers,
    )
    selected_group, group_ratio = select_group_ratio(group_ratios, group)
    return UpstreamPricing(
        group=selected_group,
        group_ratio=group_ratio,
        group_ratios=group_ratios,
        models=parse_model_prices(payload),
    )


def parse_group_ratios(payload: Mapping[str, Any]) -> dict[str, Decimal]:
    """Read the ``group_ratio`` map from either upstream payload shape."""

    data = payload.get("data")
    sources: list[Mapping[str, Any]] = [payload]
    if isinstance(data, Mapping):
        sources.append(data)
    for source in sources:
        ratios = _ratio_map(source.get("group_ratio"))
        if ratios:
            return ratios
    return {}


def select_group_ratio(group_ratios: Mapping[str, Decimal], group: str) -> tuple[str, Decimal]:
    """Pick the ratio for ``group``, falling back to the default group and then to 1."""

    if group in group_ratios:
        return group, group_ratios[group]
    if DEFAULT_PRICE_GROUP in group_ratios:
        return DEFAULT_PRICE_GROUP, group_ratios[DEFAULT_PRICE_GROUP]
    return group, Decimal("1")


def parse_model_prices(payload: Mapping[str, Any]) -> dict[str, UpstreamModelPrice]:
    """Read per-model ratios from either the pricing list or the ratio map shape."""

    data = payload.get("data")
    if isinstance(data, list):
        return _parse_pricing_list(data)
    if isinstance(data, Mapping) and "model_ratio" in data:
        return _parse_ratio_map(data)
    raise ModelPriceError("Upstream price list has an unsupported shape")


def convert_ratio_prices(price: UpstreamModelPrice) -> UpstreamModelPrice:
    """Derive per-million-token list prices from a model's upstream ratios."""

    if price.quota_type != 0 or price.model_ratio is None:
        return price
    input_price = _quantize(price.model_ratio * RATIO_PRICE_FACTOR)
    completion_ratio = price.completion_ratio if price.completion_ratio is not None else Decimal(1)
    return UpstreamModelPrice(
        model_name=price.model_name,
        quota_type=price.quota_type,
        model_ratio=price.model_ratio,
        completion_ratio=completion_ratio,
        input_price_per_million=input_price,
        output_price_per_million=_quantize(input_price * completion_ratio),
    )


def truncate_price_error(message: str) -> str:
    return truncate_balance_error(message)[:MAX_PRICE_ERROR_CHARS]


def _parse_pricing_list(entries: list[Any]) -> dict[str, UpstreamModelPrice]:
    models: dict[str, UpstreamModelPrice] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("model_name")
        if not isinstance(name, str) or not name:
            continue
        model_ratio = _optional_ratio(entry.get("model_ratio"))
        fixed_price = _optional_ratio(entry.get("model_price"))
        completion_ratio = _optional_ratio(entry.get("completion_ratio"))
        quota_type = _quota_type(entry.get("quota_type"), fixed_price=fixed_price)
        if quota_type == 0:
            if model_ratio is None or model_ratio <= 0:
                # new-api reports 0 for models whose pricing was never configured.
                continue
        elif fixed_price is None or fixed_price <= 0:
            continue
        models[name] = convert_ratio_prices(
            UpstreamModelPrice(
                model_name=name,
                quota_type=quota_type,
                model_ratio=model_ratio,
                completion_ratio=completion_ratio,
                fixed_price=None if quota_type == 0 else fixed_price,
            )
        )
    if not models:
        raise ModelPriceError("Upstream price list does not contain any model ratios")
    return models


def _parse_ratio_map(data: Mapping[str, Any]) -> dict[str, UpstreamModelPrice]:
    model_ratios = _ratio_map(data.get("model_ratio"))
    completion_ratios = _ratio_map(data.get("completion_ratio"))
    fixed_prices = _ratio_map(data.get("model_price"))
    names = set(model_ratios) | set(fixed_prices)
    if not names:
        raise ModelPriceError("Upstream price list does not contain any model ratios")
    models: dict[str, UpstreamModelPrice] = {}
    for name in names:
        model_ratio = model_ratios.get(name)
        if model_ratio is not None and model_ratio <= 0:
            model_ratio = None
        fixed_price = fixed_prices.get(name)
        if fixed_price is not None and fixed_price <= 0:
            fixed_price = None
        if model_ratio is None and fixed_price is None:
            continue
        quota_type = 1 if model_ratio is None else 0
        models[name] = convert_ratio_prices(
            UpstreamModelPrice(
                model_name=name,
                quota_type=quota_type,
                model_ratio=model_ratio,
                completion_ratio=completion_ratios.get(name),
                fixed_price=None if quota_type == 0 else fixed_price,
            )
        )
    return models


async def _resolve_group(
    *,
    base_url: str,
    credential: ProviderCredential,
    protocol: Protocol,
    client: AsyncHttpClient,
    user_id: str | None,
    extra_headers: Mapping[str, str] | None,
) -> str:
    """Read the token's own group, tolerating upstreams that reject the probe."""

    headers = _request_headers(credential, protocol, extra_headers)
    if user_id:
        headers["New-Api-User"] = user_id
    try:
        response = await client.send(httpx.Request("GET", self_url(base_url), headers=headers))
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return DEFAULT_PRICE_GROUP
    if not isinstance(payload, Mapping):
        return DEFAULT_PRICE_GROUP
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return DEFAULT_PRICE_GROUP
    group = data.get("group")
    if not isinstance(group, str) or not group.strip():
        return DEFAULT_PRICE_GROUP
    return group.strip()


def _request_headers(
    credential: ProviderCredential,
    protocol: Protocol,
    extra_headers: Mapping[str, str] | None,
) -> httpx.Headers:
    headers = httpx.Headers(credential.auth_headers(protocol))
    if extra_headers:
        headers.update(dict(extra_headers))
    return headers


def _json_object(response: httpx.Response, *, source: str) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError:
        raise ModelPriceError(f"Upstream {source} response is not valid JSON") from None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ModelPriceError(f"Upstream {source} response must be a JSON object")
    return value


def _ratio_map(value: object) -> dict[str, Decimal]:
    if not isinstance(value, Mapping):
        return {}
    ratios: dict[str, Decimal] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        ratio = _optional_ratio(item)
        if ratio is not None:
            ratios[key] = ratio
    return ratios


def _optional_ratio(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, float):
        parsed = Decimal(str(value))
    elif isinstance(value, str):
        try:
            parsed = Decimal(value.strip())
        except InvalidOperation:
            return None
    else:
        return None
    if not parsed.is_finite() or parsed < 0 or parsed > _RATIO_LIMIT:
        return None
    return parsed


def _quota_type(value: object, *, fixed_price: Decimal | None) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value in (0, 1):
        return value
    if isinstance(value, str) and value.strip() in ("0", "1"):
        return int(value.strip())
    return 1 if fixed_price is not None and fixed_price > 0 else 0


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_PRICE_QUANTUM)


def _host_root(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if not base:
        raise ModelPriceError("Provider base URL is required to read upstream prices")
    for suffix in _BASE_URL_SUFFIXES:
        if base.endswith(suffix):
            return base[: -len(suffix)].rstrip("/")
    return base
