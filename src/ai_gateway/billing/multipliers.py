from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_gateway.db.models import Model, Provider


def get_effective_multipliers(
    model: "Model | object | None",
    provider: "Provider | object | None",
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Extract price multipliers from Model and Provider objects.

    Args:
        model: A Model (or any object with a ``price_multiplier`` attribute),
            or None. Objects without a ``price_multiplier`` attribute (e.g.
            internal recovery stubs) default to ``Decimal("1.00")``.
        provider: A Provider (or any object with ``public_multiplier`` and
            ``cost_multiplier`` attributes), or None.

    Returns:
        Tuple of (model_multiplier, public_multiplier, cost_multiplier).
        Defaults to ``Decimal("1.00")`` for either value when the
        corresponding object is None or lacks the attribute.
    """
    model_multiplier = (
        getattr(model, "price_multiplier", Decimal("1.00")) if model else Decimal("1.00")
    )
    public_multiplier = (
        getattr(provider, "public_multiplier", Decimal("1.00")) if provider else Decimal("1.00")
    )
    cost_multiplier = (
        getattr(provider, "cost_multiplier", Decimal("1.00")) if provider else Decimal("1.00")
    )
    return (model_multiplier, public_multiplier, cost_multiplier)
