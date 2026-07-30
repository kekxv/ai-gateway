from decimal import Decimal
from types import SimpleNamespace

from ai_gateway.billing.multipliers import get_effective_multipliers
from ai_gateway.db.models import Model, Provider


class TestGetEffectiveMultipliers:
    """Test multiplier extraction from Model and Provider objects."""

    def test_extracts_all_multipliers(self):
        """Extract model, public, and cost multipliers."""
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
            public_multiplier=Decimal("2.00"),
            cost_multiplier=Decimal("0.80"),
        )

        model_mult, public_mult, cost_mult = get_effective_multipliers(model, provider)

        assert model_mult == Decimal("1.50")
        assert public_mult == Decimal("2.00")
        assert cost_mult == Decimal("0.80")

    def test_none_model_returns_default(self):
        """Return Decimal('1.00') when model is None."""
        provider = Provider(
            id=1,
            name="test-provider",
            enabled=True,
            public_multiplier=Decimal("2.00"),
            cost_multiplier=Decimal("0.80"),
        )

        model_mult, public_mult, cost_mult = get_effective_multipliers(None, provider)

        assert model_mult == Decimal("1.00")
        assert public_mult == Decimal("2.00")
        assert cost_mult == Decimal("0.80")

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

        model_mult, public_mult, cost_mult = get_effective_multipliers(model, None)

        assert model_mult == Decimal("1.50")
        assert public_mult == Decimal("1.00")
        assert cost_mult == Decimal("1.00")

    def test_both_none_returns_defaults(self):
        """Return three Decimal('1.00') values when both are None."""
        model_mult, public_mult, cost_mult = get_effective_multipliers(None, None)

        assert model_mult == Decimal("1.00")
        assert public_mult == Decimal("1.00")
        assert cost_mult == Decimal("1.00")

    def test_various_multiplier_values(self):
        """Extract different multiplier values correctly."""
        test_cases = [
            (Decimal("0.50"), Decimal("0.80")),
            (Decimal("1.00"), Decimal("1.00")),
            (Decimal("1.50"), Decimal("2.00")),
            (Decimal("10.00"), Decimal("10.00")),
        ]

        for model_mult, public_mult in test_cases:
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
                public_multiplier=public_mult,
                cost_multiplier=Decimal("0.75"),
            )

            result_model, result_public, result_cost = get_effective_multipliers(
                model, provider
            )

            assert result_model == model_mult
            assert result_public == public_mult
            assert result_cost == Decimal("0.75")

    def test_returns_tuple(self):
        """Return value is a tuple."""
        result = get_effective_multipliers(None, None)
        assert isinstance(result, tuple)
        assert len(result) == 3


def test_provider_public_and_cost_multipliers_are_independent() -> None:
    model = SimpleNamespace(price_multiplier=Decimal("1.50"))
    provider = SimpleNamespace(
        public_multiplier=Decimal("2.00"),
        cost_multiplier=Decimal("0.80"),
    )

    assert get_effective_multipliers(model, provider) == (
        Decimal("1.50"),
        Decimal("2.00"),
        Decimal("0.80"),
    )
