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


@overload
def calculate_cost(model: PricedModel, usage: CanonicalUsage, /) -> Decimal: ...


@overload
def calculate_cost(
    *,
    input_price: Decimal,
    output_price: Decimal,
    usage: CanonicalUsage,
) -> Decimal: ...


def calculate_cost(
    model: PricedModel | None = None,
    usage: CanonicalUsage | None = None,
    *,
    input_price: Decimal | None = None,
    output_price: Decimal | None = None,
) -> Decimal:
    """Calculate a model charge using only Decimal arithmetic.

    Catalog prices are expressed per million tokens. The final combined charge is
    rounded once to the ledger's eight-decimal precision using ROUND_HALF_UP.
    """

    if usage is None:
        raise TypeError("usage is required")
    validate_usage(usage)
    if model is not None:
        if input_price is not None or output_price is not None:
            raise TypeError("provide either model or explicit prices, not both")
        input_price = model.input_price_per_million
        output_price = model.output_price_per_million
    if input_price is None or output_price is None:
        raise TypeError("model or both input_price and output_price are required")
    if input_price < 0 or output_price < 0:
        raise ValueError("token prices must be nonnegative")

    unrounded = (
        Decimal(usage.input_tokens) * input_price + Decimal(usage.output_tokens) * output_price
    ) / TOKENS_PER_MILLION
    return unrounded.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
