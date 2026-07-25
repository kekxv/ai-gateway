from decimal import Decimal

from ai_gateway.billing.multipliers import get_effective_multipliers
from ai_gateway.db.models import Model, Provider


class TestGetEffectiveMultipliers:
    """Test multiplier extraction from Model and Provider objects."""

    def test_extracts_both_multipliers(self):
        """Extract multipliers from both Model and Provider."""
        model = Model(
            id=1,
            canonical_name="test-model",
            display_name="Test Model",
            input_price_per_million=Decimal("10.00"),
            output_price_per_million=Decimal("20.00"),
            price_multiplier=Decimal("1.50"),
            enabled=True,
        )
        provider = Provider(
            id=1,
            name="test-provider",
            enabled=True,
            price_multiplier=Decimal("2.00"),
        )

        model_mult, provider_mult = get_effective_multipliers(model, provider)

        assert model_mult == Decimal("1.50")
        assert provider_mult == Decimal("2.00")

    def test_none_model_returns_default(self):
        """Return Decimal('1.00') when model is None."""
        provider = Provider(
            id=1,
            name="test-provider",
            enabled=True,
            price_multiplier=Decimal("2.00"),
        )

        model_mult, provider_mult = get_effective_multipliers(None, provider)

        assert model_mult == Decimal("1.00")
        assert provider_mult == Decimal("2.00")

    def test_none_provider_returns_default(self):
        """Return Decimal('1.00') when provider is None."""
        model = Model(
            id=1,
            canonical_name="test-model",
            display_name="Test Model",
            input_price_per_million=Decimal("10.00"),
            output_price_per_million=Decimal("20.00"),
            price_multiplier=Decimal("1.50"),
            enabled=True,
        )

        model_mult, provider_mult = get_effective_multipliers(model, None)

        assert model_mult == Decimal("1.50")
        assert provider_mult == Decimal("1.00")

    def test_both_none_returns_defaults(self):
        """Return (Decimal('1.00'), Decimal('1.00')) when both are None."""
        model_mult, provider_mult = get_effective_multipliers(None, None)

        assert model_mult == Decimal("1.00")
        assert provider_mult == Decimal("1.00")

    def test_various_multiplier_values(self):
        """Extract different multiplier values correctly."""
        test_cases = [
            (Decimal("0.50"), Decimal("0.80")),
            (Decimal("1.00"), Decimal("1.00")),
            (Decimal("1.50"), Decimal("2.00")),
            (Decimal("10.00"), Decimal("10.00")),
        ]

        for model_mult, provider_mult in test_cases:
            model = Model(
                id=1,
                canonical_name="test-model",
                display_name="Test Model",
                input_price_per_million=Decimal("10.00"),
                output_price_per_million=Decimal("20.00"),
                price_multiplier=model_mult,
                enabled=True,
            )
            provider = Provider(
                id=1,
                name="test-provider",
                enabled=True,
                price_multiplier=provider_mult,
            )

            result_model, result_provider = get_effective_multipliers(model, provider)

            assert result_model == model_mult
            assert result_provider == provider_mult

    def test_returns_tuple(self):
        """Return value is a tuple."""
        result = get_effective_multipliers(None, None)
        assert isinstance(result, tuple)
        assert len(result) == 2
