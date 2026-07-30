from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, overload

from ai_gateway.protocols.base import validate_usage
from ai_gateway.protocols.types import CanonicalUsage

MONEY_QUANTUM = Decimal("0.00000001")
TOKENS_PER_MILLION = Decimal("1000000")


class PricedModel(Protocol):
    input_price_per_million: Decimal
    output_price_per_million: Decimal
    cache_read_price_per_million: Decimal
    cache_write_price_per_million: Decimal


class PriceTier(PricedModel, Protocol):
    max_input_tokens: int | None


def total_input_tokens(usage: CanonicalUsage) -> int:
    """Return the context length used to select a pricing tier."""

    return usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens


def select_price_tier(model: PricedModel, usage: CanonicalUsage) -> PricedModel:
    """Select the inclusive input-length tier, or use legacy model prices."""

    tiers: tuple[PriceTier, ...] | list[PriceTier] = getattr(model, "price_tiers", ())
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


@overload
def calculate_cost(
    model: PricedModel,
    usage: CanonicalUsage,
    /,
    *,
    model_multiplier: Decimal | None = None,
    provider_multiplier: Decimal | None = None,
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
        selected_price = select_price_tier(model, usage)
        input_price = selected_price.input_price_per_million
        output_price = selected_price.output_price_per_million
        cache_read_price = getattr(
            selected_price, "cache_read_price_per_million", Decimal("0")
        )
        cache_write_price = getattr(
            selected_price, "cache_write_price_per_million", Decimal("0")
        )
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
