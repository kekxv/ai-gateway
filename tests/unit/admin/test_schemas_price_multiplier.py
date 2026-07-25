"""Tests for price_multiplier field in Admin API (catalog) schemas."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_gateway.catalog.schemas import (
    ModelResponse,
    ModelUpdate,
    ProviderResponse,
    ProviderUpdate,
)


class TestProviderResponsePriceMultiplier:
    """Tests for price_multiplier on ProviderResponse."""

    def test_provider_response_includes_price_multiplier(self) -> None:
        """ProviderResponse should include price_multiplier field."""
        provider = ProviderResponse(
            id=1,
            name="test-provider",
            has_credential=True,
            enabled=True,
            auto_load_models=False,
            model_sync_interval_seconds=300,
            last_model_sync_at=None,
            protocols=[],
            price_multiplier=Decimal("1.50"),
        )
        assert hasattr(provider, "price_multiplier")
        assert provider.price_multiplier == Decimal("1.50")

    def test_provider_response_requires_price_multiplier(self) -> None:
        """ProviderResponse must require price_multiplier (no default)."""
        with pytest.raises(ValidationError):
            ProviderResponse(
                id=1,
                name="test-provider",
                has_credential=True,
                enabled=True,
                auto_load_models=False,
                model_sync_interval_seconds=300,
                last_model_sync_at=None,
                protocols=[],
            )


class TestModelResponsePriceMultiplier:
    """Tests for price_multiplier on ModelResponse."""

    def test_model_response_includes_price_multiplier(self) -> None:
        """ModelResponse should include price_multiplier field."""
        from datetime import datetime

        now = datetime(2026, 1, 1)
        model = ModelResponse(
            id=1,
            canonical_name="test-model",
            display_name="Test Model",
            input_price_per_million=Decimal("10.00"),
            output_price_per_million=Decimal("20.00"),
            enabled=True,
            aliases=[],
            routing_strategy="weighted_random",
            created_at=now,
            updated_at=now,
            price_multiplier=Decimal("2.00"),
        )
        assert hasattr(model, "price_multiplier")
        assert model.price_multiplier == Decimal("2.00")

    def test_model_response_requires_price_multiplier(self) -> None:
        """ModelResponse must require price_multiplier (no default)."""
        from datetime import datetime

        now = datetime(2026, 1, 1)
        with pytest.raises(ValidationError):
            ModelResponse(
                id=1,
                canonical_name="test-model",
                display_name="Test Model",
                input_price_per_million=Decimal("10.00"),
                output_price_per_million=Decimal("20.00"),
                enabled=True,
                aliases=[],
                routing_strategy="weighted_random",
                created_at=now,
                updated_at=now,
            )


class TestProviderUpdatePriceMultiplier:
    """Tests for price_multiplier on ProviderUpdate."""

    def test_provider_update_accepts_price_multiplier(self) -> None:
        """ProviderUpdate should accept price_multiplier."""
        update = ProviderUpdate(price_multiplier=Decimal("1.50"))
        assert update.price_multiplier == Decimal("1.50")

    def test_provider_update_price_multiplier_optional(self) -> None:
        """ProviderUpdate price_multiplier should be optional."""
        update = ProviderUpdate()
        assert update.price_multiplier is None

    def test_provider_update_validates_range(self) -> None:
        """ProviderUpdate should validate price_multiplier range [0.10, 10.00]."""
        # Valid boundary values
        ProviderUpdate(price_multiplier=Decimal("0.10"))
        ProviderUpdate(price_multiplier=Decimal("1.00"))
        ProviderUpdate(price_multiplier=Decimal("10.00"))

        # Invalid below lower bound
        with pytest.raises(ValidationError):
            ProviderUpdate(price_multiplier=Decimal("0.09"))

        # Invalid above upper bound
        with pytest.raises(ValidationError):
            ProviderUpdate(price_multiplier=Decimal("10.01"))

        # Invalid negative
        with pytest.raises(ValidationError):
            ProviderUpdate(price_multiplier=Decimal("-1.00"))


class TestModelUpdatePriceMultiplier:
    """Tests for price_multiplier on ModelUpdate."""

    def test_model_update_accepts_price_multiplier(self) -> None:
        """ModelUpdate should accept price_multiplier."""
        update = ModelUpdate(price_multiplier=Decimal("2.00"))
        assert update.price_multiplier == Decimal("2.00")

    def test_model_update_price_multiplier_optional(self) -> None:
        """ModelUpdate price_multiplier should be optional."""
        update = ModelUpdate()
        assert update.price_multiplier is None

    def test_model_update_validates_range(self) -> None:
        """ModelUpdate should validate price_multiplier range [0.10, 10.00]."""
        # Valid boundary values
        ModelUpdate(price_multiplier=Decimal("0.10"))
        ModelUpdate(price_multiplier=Decimal("1.00"))
        ModelUpdate(price_multiplier=Decimal("10.00"))

        # Invalid below lower bound
        with pytest.raises(ValidationError):
            ModelUpdate(price_multiplier=Decimal("0.09"))

        # Invalid above upper bound
        with pytest.raises(ValidationError):
            ModelUpdate(price_multiplier=Decimal("10.01"))

        # Invalid negative
        with pytest.raises(ValidationError):
            ModelUpdate(price_multiplier=Decimal("-1.00"))
