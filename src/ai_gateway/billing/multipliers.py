from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_gateway.db.models import Model, Provider


def get_effective_multipliers(
    model: "Model | object | None",
    provider: "Provider | object | None",
) -> tuple[Decimal, Decimal]:
    """
    Extract price multipliers from Model and Provider objects.

    Args:
        model: A Model (or any object with a ``price_multiplier`` attribute),
            or None. Objects without a ``price_multiplier`` attribute (e.g.
            internal recovery stubs) default to ``Decimal("1.00")``.
        provider: A Provider (or any object with a ``price_multiplier``
            attribute), or None.

    Returns:
        Tuple of (model_multiplier, provider_multiplier).
        Defaults to ``Decimal("1.00")`` for either value when the
        corresponding object is None or lacks the attribute.
    """
    model_multiplier = (
        getattr(model, "price_multiplier", Decimal("1.00")) if model else Decimal("1.00")
    )
    provider_multiplier = (
        getattr(provider, "price_multiplier", Decimal("1.00")) if provider else Decimal("1.00")
    )
    return (model_multiplier, provider_multiplier)
