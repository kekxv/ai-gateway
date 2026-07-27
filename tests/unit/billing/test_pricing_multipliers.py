"""Tests for price multiplier support in calculate_cost()."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ai_gateway.billing.pricing import calculate_cost
from ai_gateway.db.models import Model
from ai_gateway.protocols.types import CanonicalUsage


@pytest.fixture()
def sample_model() -> Model:
    """Create a sample model for testing.

    Prices per 1M tokens:
      input:  $10.00000000
      output: $20.00000000
    """
    return Model(
        canonical_name="test-model",
        display_name="Test Model",
        input_price_per_million=Decimal("10.00000000"),
        output_price_per_million=Decimal("20.00000000"),
    )


@pytest.fixture()
def usage_1k_500() -> CanonicalUsage:
    return CanonicalUsage(input_tokens=1_000, output_tokens=500)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Existing behaviour must not change when multipliers are absent."""

    def test_no_multipliers_positional_model(
        self, sample_model: Model, usage_1k_500: CanonicalUsage
    ) -> None:
        cost = calculate_cost(sample_model, usage_1k_500)
        # (10 * 1000 + 20 * 500) / 1M = 20000 / 1M = 0.02
        assert cost == Decimal("0.02000000")

    def test_no_multipliers_explicit_prices(self, usage_1k_500: CanonicalUsage) -> None:
        cost = calculate_cost(
            input_price=Decimal("10.00000000"),
            output_price=Decimal("20.00000000"),
            usage=usage_1k_500,
        )
        assert cost == Decimal("0.02000000")


# ---------------------------------------------------------------------------
# model_multiplier
# ---------------------------------------------------------------------------


class TestModelMultiplier:
    def test_model_multiplier_only(self, sample_model: Model, usage_1k_500: CanonicalUsage) -> None:
        cost = calculate_cost(
            sample_model,
            usage_1k_500,
            model_multiplier=Decimal("1.50"),
        )
        # 0.02 * 1.5 = 0.03
        assert cost == Decimal("0.03000000")

    def test_model_multiplier_with_explicit_prices(self, usage_1k_500: CanonicalUsage) -> None:
        cost = calculate_cost(
            input_price=Decimal("10.00000000"),
            output_price=Decimal("20.00000000"),
            usage=usage_1k_500,
            model_multiplier=Decimal("1.50"),
        )
        assert cost == Decimal("0.03000000")


# ---------------------------------------------------------------------------
# provider_multiplier
# ---------------------------------------------------------------------------


class TestProviderMultiplier:
    def test_provider_multiplier_only(
        self, sample_model: Model, usage_1k_500: CanonicalUsage
    ) -> None:
        cost = calculate_cost(
            sample_model,
            usage_1k_500,
            provider_multiplier=Decimal("2.00"),
        )
        # 0.02 * 2.0 = 0.04
        assert cost == Decimal("0.04000000")


# ---------------------------------------------------------------------------
# Both multipliers
# ---------------------------------------------------------------------------


class TestBothMultipliers:
    def test_both_multipliers(self, sample_model: Model, usage_1k_500: CanonicalUsage) -> None:
        cost = calculate_cost(
            sample_model,
            usage_1k_500,
            model_multiplier=Decimal("1.50"),
            provider_multiplier=Decimal("2.00"),
        )
        # 0.02 * 1.5 * 2.0 = 0.06
        assert cost == Decimal("0.06000000")

    def test_both_multipliers_apply_after_all_cache_buckets(self) -> None:
        cost = calculate_cost(
            input_price=Decimal("2.00000000"),
            output_price=Decimal("20.00000000"),
            cache_read_price=Decimal("5.00000000"),
            cache_write_price=Decimal("10.00000000"),
            usage=CanonicalUsage(1_000_000, 1_000_000, 1_000_000, 1_000_000),
            model_multiplier=Decimal("1.50"),
            provider_multiplier=Decimal("2.00"),
        )

        assert cost == Decimal("111.00000000")


# ---------------------------------------------------------------------------
# Edge / special cases
# ---------------------------------------------------------------------------


class TestMultiplierEdgeCases:
    def test_none_multipliers_same_as_no_multipliers(
        self, sample_model: Model, usage_1k_500: CanonicalUsage
    ) -> None:
        cost_without = calculate_cost(sample_model, usage_1k_500)
        cost_with_none = calculate_cost(
            sample_model,
            usage_1k_500,
            model_multiplier=None,
            provider_multiplier=None,
        )
        assert cost_without == cost_with_none

    def test_multiplier_of_one_no_change(
        self, sample_model: Model, usage_1k_500: CanonicalUsage
    ) -> None:
        cost_without = calculate_cost(sample_model, usage_1k_500)
        cost_with_one = calculate_cost(
            sample_model,
            usage_1k_500,
            model_multiplier=Decimal("1.00"),
            provider_multiplier=Decimal("1.00"),
        )
        assert cost_without == cost_with_one

    def test_result_still_quantized(self, sample_model: Model) -> None:
        usage = CanonicalUsage(input_tokens=1_234_567, output_tokens=7_654_321)
        cost = calculate_cost(
            sample_model,
            usage,
            model_multiplier=Decimal("1.23456789"),
            provider_multiplier=Decimal("9.87654321"),
        )
        # Must fit in 8 decimal places
        assert cost == cost.quantize(Decimal("0.00000001"))

    def test_discount_multiplier(self, sample_model: Model, usage_1k_500: CanonicalUsage) -> None:
        cost = calculate_cost(
            sample_model,
            usage_1k_500,
            model_multiplier=Decimal("0.80"),
        )
        # 0.02 * 0.8 = 0.016
        assert cost == Decimal("0.01600000")

    def test_multiplier_zero_gives_zero(
        self, sample_model: Model, usage_1k_500: CanonicalUsage
    ) -> None:
        cost = calculate_cost(
            sample_model,
            usage_1k_500,
            model_multiplier=Decimal("0"),
        )
        assert cost == Decimal("0.00000000")

    def test_multiplier_keywords_only(
        self, sample_model: Model, usage_1k_500: CanonicalUsage
    ) -> None:
        """Multipliers must be keyword-only arguments (after *)."""
        # Passing as positional should raise TypeError
        with pytest.raises(TypeError):
            calculate_cost(  # type: ignore[call-arg]
                sample_model,
                usage_1k_500,
                Decimal("1.50"),  # positional model_multiplier — should fail
            )
