from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, cast, overload

from sqlalchemy.orm.exc import DetachedInstanceError

from ai_gateway.protocols.base import validate_usage
from ai_gateway.protocols.types import CanonicalUsage

MONEY_QUANTUM = Decimal("0.00000001")
TOKENS_PER_MILLION = Decimal("1000000")
BEIJING_TIMEZONE = "Asia/Shanghai"


class PricedModel(Protocol):
    input_price_per_million: Decimal
    output_price_per_million: Decimal
    cache_read_price_per_million: Decimal
    cache_write_price_per_million: Decimal


class PriceTier(PricedModel, Protocol):
    max_input_tokens: int | None


class TimePriceRule(PricedModel, Protocol):
    weekdays: int
    start_time: time
    end_time: time


def total_input_tokens(usage: CanonicalUsage) -> int:
    """Return the context length used to select a pricing tier."""

    return usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens


def select_price_tier(model: PricedModel, usage: CanonicalUsage) -> PricedModel:
    """Select the inclusive input-length tier, or use legacy model prices."""

    try:
        tiers: tuple[PriceTier, ...] | list[PriceTier] = getattr(model, "price_tiers", ())
    except DetachedInstanceError:
        # Pricing is synchronous and must never trigger ORM I/O. Gateway catalog
        # lookups eager-load tiers; detached legacy models have no loaded tier
        # collection and therefore retain their base-price fallback.
        tiers = ()
    if not tiers:
        return model

    length = total_input_tokens(usage)
    ordered = sorted(
        tiers,
        key=lambda tier: (
            tier.max_input_tokens is None,
            tier.max_input_tokens or 0,
        ),
    )
    for tier in ordered:
        if tier.max_input_tokens is None or length <= tier.max_input_tokens:
            return tier

    raise ValueError("model price tiers do not include an unbounded tier")


def select_time_price_rule(model: PricedModel, at: datetime) -> TimePriceRule | None:
    """Return the configured Beijing-time rule matching the timestamp."""

    from zoneinfo import ZoneInfo

    if at.tzinfo is None:
        raise ValueError("pricing timestamp must be timezone-aware")
    local = at.astimezone(ZoneInfo(BEIJING_TIMEZONE))
    weekday_mask = 1 << local.weekday()
    try:
        rules = cast(
            tuple[TimePriceRule, ...] | list[TimePriceRule],
            getattr(model, "time_price_rules", ()),
        )
    except DetachedInstanceError:
        # Time pricing, like tier pricing, must not cause implicit ORM I/O.
        # Detached legacy callers retain the base-price fallback when the
        # relationship was not preloaded.
        rules = ()
    for rule in rules:
        effective_at = getattr(rule, "effective_at", None)
        if (
            rule.weekdays & weekday_mask
            and (
                effective_at is None or at.replace(tzinfo=None) >= effective_at.replace(tzinfo=None)
            )
            and rule.start_time <= local.time() < rule.end_time
        ):
            return rule
    return None


@overload
def calculate_cost(
    model: PricedModel,
    usage: CanonicalUsage,
    /,
    *,
    model_multiplier: Decimal | None = None,
    provider_multiplier: Decimal | None = None,
    at: datetime | None = None,
) -> Decimal: ...


@overload
def calculate_cost(
    *,
    input_price: Decimal,
    output_price: Decimal,
    cache_read_price: Decimal = Decimal("0"),
    cache_write_price: Decimal = Decimal("0"),
    usage: CanonicalUsage,
    model_multiplier: Decimal | None = None,
    provider_multiplier: Decimal | None = None,
    at: datetime | None = None,
) -> Decimal: ...


def calculate_cost(
    model: PricedModel | None = None,
    usage: CanonicalUsage | None = None,
    *,
    input_price: Decimal | None = None,
    output_price: Decimal | None = None,
    cache_read_price: Decimal | None = None,
    cache_write_price: Decimal | None = None,
    model_multiplier: Decimal | None = None,
    provider_multiplier: Decimal | None = None,
    at: datetime | None = None,
) -> Decimal:
    """Calculate a model charge using only Decimal arithmetic.

    Catalog prices are expressed per million tokens. Optional ``model_multiplier``
    and ``provider_multiplier`` are applied multiplicatively to the base cost
    before final quantization. When both are supplied the effective multiplier
    is ``model_multiplier * provider_multiplier``. ``None`` values are ignored,
    preserving backward compatibility with callers that do not pass multipliers.
    The final combined charge is rounded once to the ledger's eight-decimal
    precision using ROUND_HALF_UP.
    """

    if usage is None:
        raise TypeError("usage is required")
    validate_usage(usage)
    if model is not None:
        if any(
            price is not None
            for price in (
                input_price,
                output_price,
                cache_read_price,
                cache_write_price,
            )
        ):
            raise TypeError("provide either model or explicit prices, not both")
        selected_time_price = select_time_price_rule(model, at or datetime.now(UTC))
        selected_price = (
            select_price_tier(model, usage) if selected_time_price is None else selected_time_price
        )
        input_price = selected_price.input_price_per_million
        output_price = selected_price.output_price_per_million
        cache_read_price = getattr(selected_price, "cache_read_price_per_million", Decimal("0"))
        cache_write_price = getattr(selected_price, "cache_write_price_per_million", Decimal("0"))
    if input_price is None or output_price is None:
        raise TypeError("model or both input_price and output_price are required")
    cache_read_price = Decimal("0") if cache_read_price is None else cache_read_price
    cache_write_price = Decimal("0") if cache_write_price is None else cache_write_price
    if any(
        price < 0
        for price in (
            input_price,
            output_price,
            cache_read_price,
            cache_write_price,
        )
    ):
        raise ValueError("token prices must be nonnegative")

    unrounded = (
        Decimal(usage.input_tokens) * input_price
        + Decimal(usage.output_tokens) * output_price
        + Decimal(usage.cache_read_tokens) * cache_read_price
        + Decimal(usage.cache_write_tokens) * cache_write_price
    ) / TOKENS_PER_MILLION

    if model_multiplier is not None:
        unrounded *= model_multiplier
    if provider_multiplier is not None:
        unrounded *= provider_multiplier

    return unrounded.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
