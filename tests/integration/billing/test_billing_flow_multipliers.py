"""Integration tests for billing flow with price multipliers.

Verifies that the end-to-end billing calculation correctly applies
``price_multiplier`` values from both ``Provider`` and ``Model`` ORM objects,
using ``get_effective_multipliers`` to extract them and ``calculate_cost`` to
compute the final charge.

The formula under test is:
    final_cost = base_cost * model_multiplier * provider_multiplier

where base_cost is computed from catalog prices and token usage.
"""

from __future__ import annotations

from decimal import Decimal

from ai_gateway.billing.multipliers import get_effective_multipliers
from ai_gateway.billing.pricing import calculate_cost
from ai_gateway.db.models import Model, Provider
from ai_gateway.protocols.types import CanonicalUsage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(
    *,
    id: int = 1,
    name: str = "test-provider",
    public_multiplier: Decimal = Decimal("1.00"),
    cost_multiplier: Decimal = Decimal("1.00"),
) -> Provider:
    """Build an in-memory Provider (no DB flush)."""
    return Provider(
        id=id,
        name=name,
        credential_encrypted=b"test-secret",
        enabled=True,
        public_multiplier=public_multiplier,
        cost_multiplier=cost_multiplier,
    )


def _make_model(
    *,
    id: int = 1,
    canonical_name: str = "test-model",
    display_name: str = "Test Model",
    input_price_per_million: Decimal = Decimal("10.00"),
    output_price_per_million: Decimal = Decimal("20.00"),
    price_multiplier: Decimal = Decimal("1.00"),
) -> Model:
    """Build an in-memory Model (no DB flush)."""
    return Model(
        id=id,
        canonical_name=canonical_name,
        display_name=display_name,
        input_price_per_million=input_price_per_million,
        output_price_per_million=output_price_per_million,
        price_multiplier=price_multiplier,
        enabled=True,
    )


# 1M input + 1M output at $10/$20 per million => base_cost == $30
ONE_MILLION_USAGE = CanonicalUsage(input_tokens=1_000_000, output_tokens=1_000_000)
BASE_COST = Decimal("30.00000000")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBillingFlowWithMultipliers:
    """Integration tests for billing flow with price multipliers."""

    def test_provider_multiplier_applied_to_billing(self) -> None:
        """Verify provider multiplier is applied during billing."""
        provider = _make_provider(public_multiplier=Decimal("1.50"))
        model = _make_model(price_multiplier=Decimal("1.00"))

        model_mult, provider_mult, _ = get_effective_multipliers(model, provider)

        cost = calculate_cost(
            model,
            ONE_MILLION_USAGE,
            model_multiplier=model_mult,
            provider_multiplier=provider_mult,
        )

        # Expected: base=30, with 1.50 provider multiplier: 30 * 1.50 = 45
        assert cost == Decimal("45.00000000")

    def test_model_multiplier_applied_to_billing(self) -> None:
        """Verify model multiplier is applied during billing."""
        provider = _make_provider(public_multiplier=Decimal("1.00"))
        model = _make_model(price_multiplier=Decimal("2.00"))

        model_mult, provider_mult, _ = get_effective_multipliers(model, provider)

        cost = calculate_cost(
            model,
            ONE_MILLION_USAGE,
            model_multiplier=model_mult,
            provider_multiplier=provider_mult,
        )

        # Expected: 30 * 2.00 = 60
        assert cost == Decimal("60.00000000")

    def test_both_multipliers_applied_multiplicatively(self) -> None:
        """Verify both multipliers are applied multiplicatively."""
        provider = _make_provider(public_multiplier=Decimal("1.50"))
        model = _make_model(price_multiplier=Decimal("2.00"))

        model_mult, provider_mult, _ = get_effective_multipliers(model, provider)

        cost = calculate_cost(
            model,
            ONE_MILLION_USAGE,
            model_multiplier=model_mult,
            provider_multiplier=provider_mult,
        )

        # Expected: 30 * 2.00 * 1.50 = 90
        assert cost == Decimal("90.00000000")

    def test_default_multipliers_are_one(self) -> None:
        """Verify default multipliers are 1.00."""
        provider = _make_provider(public_multiplier=Decimal("1.00"))
        model = _make_model(price_multiplier=Decimal("1.00"))

        model_mult, provider_mult, _ = get_effective_multipliers(model, provider)

        cost = calculate_cost(
            model,
            ONE_MILLION_USAGE,
            model_multiplier=model_mult,
            provider_multiplier=provider_mult,
        )

        # Expected: 30 * 1.00 * 1.00 = 30
        assert cost == Decimal("30.00000000")

    def test_multiplier_formula_is_correct(self) -> None:
        """Verify the formula: final_cost = base_cost * model_mult * provider_mult."""
        test_cases: list[tuple[Decimal, Decimal, Decimal]] = [
            (Decimal("1.00"), Decimal("1.00"), Decimal("30.00000000")),
            (Decimal("1.50"), Decimal("1.00"), Decimal("45.00000000")),
            (Decimal("1.00"), Decimal("2.00"), Decimal("60.00000000")),
            (Decimal("1.50"), Decimal("2.00"), Decimal("90.00000000")),
            (Decimal("0.50"), Decimal("0.50"), Decimal("7.50000000")),  # Discount scenario
        ]

        provider = _make_provider()
        model = _make_model()

        for model_mult, provider_mult, expected in test_cases:
            provider.public_multiplier = provider_mult
            model.price_multiplier = model_mult

            extracted_model_mult, extracted_provider_mult, _ = get_effective_multipliers(
                model, provider
            )

            cost = calculate_cost(
                model,
                ONE_MILLION_USAGE,
                model_multiplier=extracted_model_mult,
                provider_multiplier=extracted_provider_mult,
            )

            assert cost == expected, (
                f"Failed for model_mult={model_mult}, provider_mult={provider_mult}: "
                f"got {cost}, expected {expected}"
            )

    def test_none_provider_defaults_to_one(self) -> None:
        """Verify None provider defaults to 1.00 multiplier."""
        model = _make_model(price_multiplier=Decimal("1.50"))

        model_mult, provider_mult, _ = get_effective_multipliers(model, None)

        cost = calculate_cost(
            model,
            ONE_MILLION_USAGE,
            model_multiplier=model_mult,
            provider_multiplier=provider_mult,
        )

        # Expected: 30 * 1.50 * 1.00 = 45
        assert cost == Decimal("45.00000000")

    def test_none_model_defaults_to_one(self) -> None:
        """Verify None model defaults to 1.00 multiplier."""
        provider = _make_provider(public_multiplier=Decimal("2.00"))

        model_mult, provider_mult, _ = get_effective_multipliers(None, provider)

        # When model is None, we can't call calculate_cost, but we verify the multiplier
        assert model_mult == Decimal("1.00")
        assert provider_mult == Decimal("2.00")

    def test_sub_million_token_usage_with_multiplier(self) -> None:
        """Verify multipliers work with sub-million token counts."""
        provider = _make_provider(public_multiplier=Decimal("1.50"))
        model = _make_model(price_multiplier=Decimal("2.00"))

        model_mult, provider_mult, _ = get_effective_multipliers(model, provider)

        # 100k input + 50k output
        usage = CanonicalUsage(input_tokens=100_000, output_tokens=50_000)
        cost = calculate_cost(
            model,
            usage,
            model_multiplier=model_mult,
            provider_multiplier=provider_mult,
        )

        # base = (10 * 100_000 + 20 * 50_000) / 1_000_000
        #      = (1_000_000 + 1_000_000) / 1_000_000 = 2
        # final = 2 * 2.00 * 1.50 = 6
        assert cost == Decimal("6.00000000")

    def test_end_to_end_flow_with_changed_multipliers(self) -> None:
        """Simulate a full flow: create objects, mutate multiplier, re-bill.

        This is the integration-level check: multipliers are read fresh from
        the ORM objects at billing time, so changing them between requests
        changes the resulting cost.
        """
        provider = _make_provider(public_multiplier=Decimal("1.00"))
        model = _make_model(price_multiplier=Decimal("1.00"))

        # First request: no markup
        m1, p1, _ = get_effective_multipliers(model, provider)
        cost1 = calculate_cost(
            model,
            ONE_MILLION_USAGE,
            model_multiplier=m1,
            provider_multiplier=p1,
        )
        assert cost1 == Decimal("30.00000000")

        # Admin raises the provider multiplier
        provider.public_multiplier = Decimal("3.00")
        # Second request: provider markup applies
        m2, p2, _ = get_effective_multipliers(model, provider)
        cost2 = calculate_cost(
            model,
            ONE_MILLION_USAGE,
            model_multiplier=m2,
            provider_multiplier=p2,
        )
        assert cost2 == Decimal("90.00000000")

        # Admin also raises the model multiplier
        model.price_multiplier = Decimal("2.00")
        # Third request: both markups apply
        m3, p3, _ = get_effective_multipliers(model, provider)
        cost3 = calculate_cost(
            model,
            ONE_MILLION_USAGE,
            model_multiplier=m3,
            provider_multiplier=p3,
        )
        assert cost3 == Decimal("180.00000000")
