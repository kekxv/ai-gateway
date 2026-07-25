from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_gateway.db.models import Model, Provider


def get_effective_multipliers(
    model: "Model | None",
    provider: "Provider | None",
) -> tuple[Decimal, Decimal]:
    """
    Extract price multipliers from Model and Provider objects.

    Args:
        model: A Model object with a ``price_multiplier`` attribute, or None.
        provider: A Provider object with a ``price_multiplier`` attribute, or None.

    Returns:
        Tuple of (model_multiplier, provider_multiplier).
        Defaults to ``Decimal("1.00")`` for either value when the
        corresponding object is None.
    """
    model_multiplier = model.price_multiplier if model else Decimal("1.00")
    provider_multiplier = provider.price_multiplier if provider else Decimal("1.00")
    return (model_multiplier, provider_multiplier)
