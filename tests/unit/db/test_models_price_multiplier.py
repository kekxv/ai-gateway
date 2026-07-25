"""Verify price_multiplier field exists on Provider and Model models.

TDD tests for Task 2 — add a ``price_multiplier`` Numeric(4, 2) column to
both the Provider and Model ORM classes. The field must default to
``Decimal("1.00")`` at the ORM layer and carry a ``server_default=text("1.00")``
for the database-level default.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped

from ai_gateway.db.models import Model, Provider


# ---------------------------------------------------------------------------
# Attribute presence
# ---------------------------------------------------------------------------


class TestPriceMultiplierPresence:
    """Verify the column attribute is present on both ORM classes."""

    def test_provider_has_price_multiplier_attribute(self) -> None:
        """Provider model should expose a price_multiplier attribute."""
        assert hasattr(Provider, "price_multiplier")

    def test_model_has_price_multiplier_attribute(self) -> None:
        """Model model should expose a price_multiplier attribute."""
        assert hasattr(Model, "price_multiplier")


# ---------------------------------------------------------------------------
# Column configuration (introspected from the ORM, no DB required)
# ---------------------------------------------------------------------------


class TestPriceMultiplierColumnConfig:
    """Verify the SQLAlchemy column metadata matches the spec."""

    def test_provider_column_type_is_numeric_4_2(self) -> None:
        """Provider.price_multiplier should be Numeric(4, 2)."""
        col = Provider.__table__.columns["price_multiplier"]
        assert isinstance(col.type, Numeric)
        assert col.type.precision == 4
        assert col.type.scale == 2

    def test_model_column_type_is_numeric_4_2(self) -> None:
        """Model.price_multiplier should be Numeric(4, 2)."""
        col = Model.__table__.columns["price_multiplier"]
        assert isinstance(col.type, Numeric)
        assert col.type.precision == 4
        assert col.type.scale == 2

    def test_provider_column_is_not_nullable(self) -> None:
        """Provider.price_multiplier should be declared NOT NULL."""
        col = Provider.__table__.columns["price_multiplier"]
        assert col.nullable is False

    def test_model_column_is_not_nullable(self) -> None:
        """Model.price_multiplier should be declared NOT NULL."""
        col = Model.__table__.columns["price_multiplier"]
        assert col.nullable is False

    def test_provider_column_orm_default(self) -> None:
        """Provider.price_multiplier ORM default should be Decimal('1.00')."""
        col = Provider.__table__.columns["price_multiplier"]
        # SQLAlchemy stores the raw default (may be a callable or scalar)
        default = col.default
        assert default is not None, "expected an ORM-side default to be configured"
        # arg holds the scalar when it is not a callable
        assert default.arg == Decimal("1.00")

    def test_model_column_orm_default(self) -> None:
        """Model.price_multiplier ORM default should be Decimal('1.00')."""
        col = Model.__table__.columns["price_multiplier"]
        default = col.default
        assert default is not None, "expected an ORM-side default to be configured"
        assert default.arg == Decimal("1.00")

    def test_provider_column_server_default(self) -> None:
        """Provider.price_multiplier server_default should render as '1.00'."""
        col = Provider.__table__.columns["price_multiplier"]
        sd = col.server_default
        assert sd is not None, "expected a server_default to be configured"
        # text() defaults compile to a TextClause; the arg is the raw string
        assert "1.00" in str(sd.arg)

    def test_model_column_server_default(self) -> None:
        """Model.price_multiplier server_default should render as '1.00'."""
        col = Model.__table__.columns["price_multiplier"]
        sd = col.server_default
        assert sd is not None, "expected a server_default to be configured"
        assert "1.00" in str(sd.arg)


# ---------------------------------------------------------------------------
# Instantiation (ORM-layer only — no database round-trip)
# ---------------------------------------------------------------------------


class TestPriceMultiplierInstantiation:
    """Verify models can be created with and without price_multiplier."""

    def test_provider_instantiation_without_price_multiplier(self) -> None:
        """Provider can be constructed without passing price_multiplier."""
        provider = Provider(
            id=1,
            name="test-provider",
            credential_encrypted=b"dummy",
            enabled=True,
        )
        assert provider is not None
        # Before flushing to DB, the ORM-level default may or may not be applied
        # depending on SQLAlchemy version; we only assert the object is valid.

    def test_provider_instantiation_with_price_multiplier(self) -> None:
        """Provider can be constructed with an explicit price_multiplier."""
        provider = Provider(
            id=2,
            name="test-provider-2",
            credential_encrypted=b"dummy",
            enabled=True,
            price_multiplier=Decimal("2.50"),
        )
        assert provider.price_multiplier == Decimal("2.50")

    def test_model_instantiation_without_price_multiplier(self) -> None:
        """Model can be constructed without passing price_multiplier."""
        model = Model(
            id=1,
            canonical_name="test-model",
            display_name="Test Model",
            enabled=True,
        )
        assert model is not None

    def test_model_instantiation_with_price_multiplier(self) -> None:
        """Model can be constructed with an explicit price_multiplier."""
        model = Model(
            id=2,
            canonical_name="test-model-2",
            display_name="Test Model 2",
            enabled=True,
            price_multiplier=Decimal("0.75"),
        )
        assert model.price_multiplier == Decimal("0.75")

    def test_provider_price_multiplier_accepts_decimal_range(self) -> None:
        """Provider.price_multiplier should accept the full spec range 0.10..10.00."""
        for value in (Decimal("0.10"), Decimal("1.00"), Decimal("10.00")):
            provider = Provider(
                name=f"prov-{value}",
                credential_encrypted=b"dummy",
                price_multiplier=value,
            )
            assert provider.price_multiplier == value

    def test_model_price_multiplier_accepts_decimal_range(self) -> None:
        """Model.price_multiplier should accept the full spec range 0.10..10.00."""
        for value in (Decimal("0.10"), Decimal("1.00"), Decimal("10.00")):
            model = Model(
                canonical_name=f"model-{value}",
                display_name="Display",
                price_multiplier=value,
            )
            assert model.price_multiplier == value
