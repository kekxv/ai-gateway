from decimal import Decimal

from sqlalchemy import BigInteger, Numeric

import ai_gateway.db.models as db_models
from ai_gateway.db.models import Model, Provider, RequestLog


def test_provider_exposes_separate_cost_and_public_multiplier_columns() -> None:
    assert "price_multiplier" not in Provider.__table__.columns
    for name in ("cost_multiplier", "public_multiplier"):
        column = Provider.__table__.columns[name]
        assert isinstance(column.type, Numeric)
        assert (column.type.precision, column.type.scale) == (4, 2)
        assert column.nullable is False
        assert column.default is not None
        assert column.default.arg == Decimal("1.00")


def test_model_price_tier_has_inclusive_nullable_bound_and_exact_prices() -> None:
    assert hasattr(db_models, "ModelPriceTier")
    ModelPriceTier = db_models.ModelPriceTier
    bound = ModelPriceTier.__table__.columns["max_input_tokens"]
    assert isinstance(bound.type, BigInteger)
    assert bound.nullable is True
    for name in (
        "input_price_per_million",
        "output_price_per_million",
        "cache_read_price_per_million",
        "cache_write_price_per_million",
    ):
        column = ModelPriceTier.__table__.columns[name]
        assert isinstance(column.type, Numeric)
        assert (column.type.precision, column.type.scale) == (20, 8)

    tier = ModelPriceTier(
        max_input_tokens=272_000,
        input_price_per_million=Decimal("3"),
        output_price_per_million=Decimal("15"),
        cache_read_price_per_million=Decimal("0.30"),
        cache_write_price_per_million=Decimal("3.75"),
    )
    model = Model(canonical_name="tiered", display_name="Tiered", price_tiers=[tier])
    assert model.price_tiers[0].max_input_tokens == 272_000


def test_request_log_has_private_platform_cost_column() -> None:
    column = RequestLog.__table__.columns["cost_amount"]
    assert isinstance(column.type, Numeric)
    assert (column.type.precision, column.type.scale) == (20, 8)
    assert column.nullable is False
