from decimal import Decimal

from ai_gateway.billing.pricing import calculate_cost, select_price_tier
from ai_gateway.billing.service import DEFAULT_MAX_OUTPUT_TOKENS
from ai_gateway.core.config import Settings
from ai_gateway.db.models import Model, ModelPriceTier
from ai_gateway.protocols.types import CanonicalUsage


def test_cost_uses_decimal_without_float_rounding() -> None:
    usage = CanonicalUsage(input_tokens=1_250, output_tokens=375)

    cost = calculate_cost(
        input_price=Decimal("0.15000000"),
        output_price=Decimal("0.60000000"),
        usage=usage,
    )

    assert cost == Decimal("0.00041250")


def test_cost_accepts_catalog_model_prices() -> None:
    model = Model(
        canonical_name="priced-model",
        display_name="Priced model",
        input_price_per_million=Decimal("2.50000000"),
        output_price_per_million=Decimal("10.00000000"),
    )

    cost = calculate_cost(model, CanonicalUsage(input_tokens=2_000, output_tokens=300))

    assert cost == Decimal("0.00800000")


def test_cost_prices_cache_read_and_write_tokens_independently() -> None:
    model = Model(
        canonical_name="cache-priced-model",
        display_name="Cache priced model",
        input_price_per_million=Decimal("2.00000000"),
        output_price_per_million=Decimal("20.00000000"),
    )
    model.cache_read_price_per_million = Decimal("5.00000000")
    model.cache_write_price_per_million = Decimal("10.00000000")

    cost = calculate_cost(
        model,
        CanonicalUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_read_tokens=1_000_000,
            cache_write_tokens=1_000_000,
        ),
    )

    assert cost == Decimal("37.00000000")


def test_cost_accepts_explicit_cache_prices() -> None:
    cost = calculate_cost(
        input_price=Decimal("2.00000000"),
        output_price=Decimal("20.00000000"),
        cache_read_price=Decimal("5.00000000"),
        cache_write_price=Decimal("10.00000000"),
        usage=CanonicalUsage(1_000_000, 1_000_000, 1_000_000, 1_000_000),
    )

    assert cost == Decimal("37.00000000")


def test_cost_quantizes_half_up_to_eight_decimal_places() -> None:
    cost = calculate_cost(
        input_price=Decimal("0.00500000"),
        output_price=Decimal("0"),
        usage=CanonicalUsage(input_tokens=1, output_tokens=0),
    )

    assert cost == Decimal("0.00000001")


def test_missing_max_output_default_is_configurable_and_starts_at_4096() -> None:
    settings = Settings(
        jwt_secret="billing-unit-test-secret-at-least-32-bytes",
        encryption_key="billing-unit-test-encryption-key",
        billing_default_max_output_tokens=512,
    )

    assert DEFAULT_MAX_OUTPUT_TOKENS == 4096
    assert settings.billing_default_max_output_tokens == 512


def _tiered_model() -> Model:
    return Model(
        canonical_name="tiered-model",
        display_name="Tiered model",
        input_price_per_million=Decimal("99"),
        output_price_per_million=Decimal("99"),
        price_tiers=[
            ModelPriceTier(
                max_input_tokens=272_000,
                input_price_per_million=Decimal("1"),
                output_price_per_million=Decimal("2"),
                cache_read_price_per_million=Decimal("0.5"),
                cache_write_price_per_million=Decimal("0.75"),
            ),
            ModelPriceTier(
                max_input_tokens=None,
                input_price_per_million=Decimal("10"),
                output_price_per_million=Decimal("20"),
                cache_read_price_per_million=Decimal("5"),
                cache_write_price_per_million=Decimal("7.5"),
            ),
        ],
    )


def test_tier_boundary_is_inclusive_and_counts_all_input_context_buckets() -> None:
    model = _tiered_model()
    at_limit = CanonicalUsage(200_000, 1_000_000, 72_000, 0)
    over_limit = CanonicalUsage(200_001, 1_000_000, 72_000, 0)

    assert select_price_tier(model, at_limit).max_input_tokens == 272_000
    assert calculate_cost(model, at_limit) == Decimal("2.23600000")
    assert select_price_tier(model, over_limit).max_input_tokens is None
    assert calculate_cost(model, over_limit) == Decimal("22.36001000")


def test_output_tokens_do_not_select_the_length_tier() -> None:
    model = _tiered_model()
    usage = CanonicalUsage(input_tokens=1, output_tokens=1_000_000)

    assert select_price_tier(model, usage).max_input_tokens == 272_000
    assert calculate_cost(model, usage) == Decimal("2.00000100")


def test_model_without_tiers_uses_legacy_prices() -> None:
    model = Model(
        canonical_name="legacy-model",
        display_name="Legacy model",
        input_price_per_million=Decimal("3"),
        output_price_per_million=Decimal("4"),
    )

    assert select_price_tier(model, CanonicalUsage(1_000_000, 1_000_000)) is model
    assert calculate_cost(model, CanonicalUsage(1_000_000, 1_000_000)) == Decimal("7.00000000")
