from decimal import Decimal

from ai_gateway.billing.pricing import calculate_cost
from ai_gateway.billing.service import DEFAULT_MAX_OUTPUT_TOKENS
from ai_gateway.core.config import Settings
from ai_gateway.db.models import Model
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
