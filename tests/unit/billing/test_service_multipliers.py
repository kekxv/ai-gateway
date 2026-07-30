"""Tests for billing service integration with price multipliers.

Verifies that ``BillingService`` extracts multipliers from Model and Provider
objects and passes them through to ``calculate_cost`` when reserving and
settling requests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ai_gateway.billing.service import (
    Account,
    BalanceReservation,
    BillingService,
    LedgerEntry,
    ReservationRecovery,
    SettlementResult,
    _recovery_metadata,
    _reservation_fingerprint,
    _reservation_recovery,
    _settlement_cost,
    _settlement_costs,
    _settlement_fingerprint,
)
from ai_gateway.billing.service import (
    reserve_balance as module_reserve_balance,
)
from ai_gateway.billing.service import (
    settle_request as module_settle_request,
)
from ai_gateway.core.enums import LedgerKind, UsageSource
from ai_gateway.db.models import Model, Provider
from ai_gateway.protocols.types import CanonicalUsage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_account(*, user_id: int = 1, account_id: int = 100, balance: Decimal | None = None):
    """Build a lightweight Account-like object for mocking."""
    account = Account()
    account.id = account_id
    account.user_id = user_id
    account.balance = balance if balance is not None else Decimal("1000.00000000")
    account.total_spent = Decimal("0.00000000")
    account.version = 1
    return account


def _make_model(*, price_multiplier: Decimal = Decimal("1.50")) -> Model:
    model = Model(
        id=1,
        canonical_name="test-model",
        display_name="Test Model",
        input_price_per_million=Decimal("10.00000000"),
        output_price_per_million=Decimal("20.00000000"),
        price_multiplier=price_multiplier,
        enabled=True,
    )
    model.cache_read_price_per_million = Decimal("5.00000000")
    model.cache_write_price_per_million = Decimal("8.00000000")
    return model


def _make_provider(
    *,
    public_multiplier: Decimal = Decimal("2.00"),
    cost_multiplier: Decimal = Decimal("0.80"),
) -> Provider:
    return Provider(
        id=1,
        name="test-provider",
        enabled=True,
        public_multiplier=public_multiplier,
        cost_multiplier=cost_multiplier,
        credential_encrypted=b"fake",
    )


def _make_ledger_entry(
    *,
    entry_id: int = 1,
    account_id: int = 100,
    request_id: str | None = None,
    kind: LedgerKind = LedgerKind.RESERVATION,
    amount: Decimal = Decimal("-0.10000000"),
    balance_after: Decimal = Decimal("999.90000000"),
    metadata: dict | None = None,
) -> LedgerEntry:
    return LedgerEntry(
        id=entry_id,
        account_id=account_id,
        request_id=request_id or str(uuid4()),
        idempotency_key=f"key-{uuid4().hex[:8]}",
        kind=kind,
        amount=amount,
        balance_after=balance_after,
        metadata_json=metadata or {},
    )


def _build_session_mock(*, scalar_returns: list | None = None) -> AsyncMock:
    """Build a mock async session with chained scalar returns.

    The returned mock supports ``async with session_factory() as session`` and
    ``async with session.begin()``.  ``session.scalar`` returns values from
    ``scalar_returns`` in order via ``side_effect``.
    """
    mock_session = AsyncMock()
    # session.begin() is a SYNC method returning an async context manager.
    begin_ctx = AsyncMock()
    begin_ctx.__aenter__.return_value = None
    begin_ctx.__aexit__.return_value = None
    mock_session.begin = MagicMock(return_value=begin_ctx)
    mock_session.add = MagicMock()
    mock_session.add_all = MagicMock()
    mock_session.flush = AsyncMock()

    if scalar_returns is not None:
        mock_session.scalar.side_effect = list(scalar_returns)

    # session.scalars(...) is async (awaited), then .all() is sync.
    # await session.scalars(select(...).where(...).with_for_update()) -> entries
    # entries.all() -> list
    entries_result = MagicMock()
    entries_result.all = MagicMock(return_value=[])
    mock_session.scalars = AsyncMock(return_value=entries_result)

    return mock_session


def _build_session_factory(mock_session: AsyncMock) -> MagicMock:
    """Wrap a mock session so ``async with factory() as session`` works."""
    factory = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__.return_value = mock_session
    ctx.__aexit__.return_value = None
    factory.return_value = ctx
    return factory


# ---------------------------------------------------------------------------
# reserve_balance multiplier tests
# ---------------------------------------------------------------------------


class TestReserveWithMultipliers:
    """Verify reserve_balance passes multipliers to calculate_cost."""

    @patch("ai_gateway.billing.service._locked_account_for_user", new_callable=AsyncMock)
    @patch("ai_gateway.billing.service.get_effective_multipliers")
    @patch("ai_gateway.billing.service.calculate_cost")
    async def test_reserve_uses_maximum_eligible_public_multiplier_override(
        self,
        mock_calculate_cost: MagicMock,
        mock_get_multipliers: MagicMock,
        mock_locked_account: AsyncMock,
    ) -> None:
        model = _make_model(price_multiplier=Decimal("1.50"))
        mock_calculate_cost.return_value = Decimal("0.37500000")
        mock_get_multipliers.return_value = (
            Decimal("1.50"),
            Decimal("1.00"),
            Decimal("1.00"),
        )
        mock_locked_account.return_value = _make_account()
        mock_session = _build_session_mock(scalar_returns=[None, None])
        service = BillingService(_build_session_factory(mock_session))

        await service.reserve_balance(
            user_id=1,
            model=model,
            estimated_input_tokens=1000,
            max_output_tokens=500,
            idempotency_key=f"reserve-public-max-{uuid4().hex[:8]}",
            provider_public_multiplier=Decimal("2.50"),
        )

        mock_calculate_cost.assert_called_once_with(
            model,
            CanonicalUsage(1000, 500),
            model_multiplier=Decimal("1.50"),
            provider_multiplier=Decimal("2.50"),
        )

    @patch("ai_gateway.billing.service._locked_account_for_user", new_callable=AsyncMock)
    @patch("ai_gateway.billing.service.get_effective_multipliers")
    @patch("ai_gateway.billing.service.calculate_cost")
    async def test_reserve_includes_model_multiplier(
        self,
        mock_calculate_cost: MagicMock,
        mock_get_multipliers: MagicMock,
        mock_locked_account: AsyncMock,
    ) -> None:
        """Reserve should pass model multiplier to calculate_cost."""
        model = _make_model(price_multiplier=Decimal("1.50"))
        provider = _make_provider(public_multiplier=Decimal("2.00"))
        mock_calculate_cost.return_value = Decimal("0.10000000")
        mock_get_multipliers.return_value = (
            Decimal("1.50"),
            Decimal("2.00"),
            Decimal("0.80"),
        )
        mock_locked_account.return_value = _make_account()
        mock_session = _build_session_mock(scalar_returns=[None, None])
        service = BillingService(_build_session_factory(mock_session))

        result = await service.reserve_balance(
            user_id=1,
            model=model,
            estimated_input_tokens=1000,
            max_output_tokens=500,
            idempotency_key=f"reserve-model-{uuid4().hex[:8]}",
            provider=provider,
        )

        mock_get_multipliers.assert_called_once_with(model, provider)
        mock_calculate_cost.assert_called_once_with(
            model,
            CanonicalUsage(1000, 500),
            model_multiplier=Decimal("1.50"),
            provider_multiplier=Decimal("2.00"),
        )
        assert isinstance(result, BalanceReservation)

    @patch("ai_gateway.billing.service._locked_account_for_user", new_callable=AsyncMock)
    @patch("ai_gateway.billing.service.get_effective_multipliers")
    @patch("ai_gateway.billing.service.calculate_cost")
    async def test_reserve_with_none_provider_defaults_to_one(
        self,
        mock_calculate_cost: MagicMock,
        mock_get_multipliers: MagicMock,
        mock_locked_account: AsyncMock,
    ) -> None:
        """When provider is None, helper should still be called with None."""
        model = _make_model(price_multiplier=Decimal("1.50"))
        mock_calculate_cost.return_value = Decimal("0.10000000")
        mock_get_multipliers.return_value = (
            Decimal("1.50"),
            Decimal("1.00"),
            Decimal("1.00"),
        )
        mock_locked_account.return_value = _make_account()
        mock_session = _build_session_mock(scalar_returns=[None, None])
        service = BillingService(_build_session_factory(mock_session))

        await service.reserve_balance(
            user_id=1,
            model=model,
            estimated_input_tokens=1000,
            max_output_tokens=500,
            idempotency_key=f"reserve-none-{uuid4().hex[:8]}",
        )

        mock_get_multipliers.assert_called_once_with(model, None)
        mock_calculate_cost.assert_called_once_with(
            model,
            CanonicalUsage(1000, 500),
            model_multiplier=Decimal("1.50"),
            provider_multiplier=Decimal("1.00"),
        )

    @patch("ai_gateway.billing.service._locked_account_for_user", new_callable=AsyncMock)
    @patch("ai_gateway.billing.service.get_effective_multipliers")
    @patch("ai_gateway.billing.service.calculate_cost")
    async def test_reserve_both_multipliers_applied_multiplicatively(
        self,
        mock_calculate_cost: MagicMock,
        mock_get_multipliers: MagicMock,
        mock_locked_account: AsyncMock,
    ) -> None:
        """Both multipliers are passed to calculate_cost for multiplication."""
        model = _make_model(price_multiplier=Decimal("1.50"))
        provider = _make_provider(public_multiplier=Decimal("2.00"))
        # Effective multiplier: 1.50 * 2.00 = 3.00
        mock_calculate_cost.return_value = Decimal("0.30000000")
        mock_get_multipliers.return_value = (
            Decimal("1.50"),
            Decimal("2.00"),
            Decimal("0.80"),
        )
        mock_locked_account.return_value = _make_account()
        mock_session = _build_session_mock(scalar_returns=[None, None])
        service = BillingService(_build_session_factory(mock_session))

        await service.reserve_balance(
            user_id=1,
            model=model,
            estimated_input_tokens=1000,
            max_output_tokens=500,
            idempotency_key=f"reserve-both-{uuid4().hex[:8]}",
            provider=provider,
        )

        mock_calculate_cost.assert_called_once_with(
            model,
            CanonicalUsage(1000, 500),
            model_multiplier=Decimal("1.50"),
            provider_multiplier=Decimal("2.00"),
        )

    @patch("ai_gateway.billing.service._locked_account_for_user", new_callable=AsyncMock)
    async def test_reservation_snapshots_cache_prices(
        self,
        mock_locked_account: AsyncMock,
    ) -> None:
        model = _make_model(price_multiplier=Decimal("1.00"))
        mock_locked_account.return_value = _make_account()
        mock_session = _build_session_mock(scalar_returns=[None, None])
        service = BillingService(_build_session_factory(mock_session))

        await service.reserve_balance(
            user_id=1,
            model=model,
            estimated_input_tokens=1000,
            max_output_tokens=500,
            idempotency_key=f"reserve-cache-prices-{uuid4().hex[:8]}",
        )

        entry = mock_session.add.call_args.args[0]
        assert entry.metadata_json["cache_read_price_per_million"] == "5.00000000"
        assert entry.metadata_json["cache_write_price_per_million"] == "8.00000000"


# ---------------------------------------------------------------------------
# settle_request multiplier tests
# ---------------------------------------------------------------------------


class TestSettleWithMultipliers:
    """Verify settle_request passes multipliers through to calculate_cost."""

    async def test_settle_includes_provider_multiplier(self) -> None:
        """Settle should call calculate_cost with provider multiplier."""
        model = _make_model(price_multiplier=Decimal("1.00"))
        provider = _make_provider(public_multiplier=Decimal("2.00"))
        usage = CanonicalUsage(1000, 500)
        request_id = str(uuid4())

        with (
            patch(
                "ai_gateway.billing.service.calculate_cost",
                return_value=Decimal("0.20000000"),
            ) as mock_calc,
            patch(
                "ai_gateway.billing.service.get_effective_multipliers",
                return_value=(Decimal("1.00"), Decimal("2.00"), Decimal("0.80")),
            ) as mock_get,
        ):
            reservation_entry = _make_ledger_entry(
                entry_id=42,
                account_id=100,
                request_id=request_id,
                metadata={"recovery_pending": False},
            )
            mock_session = _build_session_mock(
                scalar_returns=[100, _make_account(account_id=100), reservation_entry, None],
            )
            service = BillingService(_build_session_factory(mock_session))

            result = await service.settle_request(
                reservation_id=42,
                idempotency_key=f"settle-{uuid4().hex[:8]}",
                model=model,
                usage=usage,
                provider=provider,
            )

        mock_get.assert_called_once_with(model, provider)
        mock_calc.assert_any_call(
            model,
            usage,
            model_multiplier=Decimal("1.00"),
            provider_multiplier=Decimal("2.00"),
        )
        assert mock_calc.call_count == 2
        assert isinstance(result, SettlementResult)

    async def test_settle_with_none_provider_defaults_to_one(self) -> None:
        """When provider is None, provider_multiplier should be Decimal('1.00')."""
        model = _make_model(price_multiplier=Decimal("1.50"))
        usage = CanonicalUsage(1000, 500)
        request_id = str(uuid4())

        with (
            patch(
                "ai_gateway.billing.service.calculate_cost",
                return_value=Decimal("0.15000000"),
            ) as mock_calc,
            patch(
                "ai_gateway.billing.service.get_effective_multipliers",
                return_value=(Decimal("1.50"), Decimal("1.00"), Decimal("1.00")),
            ) as mock_get,
        ):
            reservation_entry = _make_ledger_entry(
                entry_id=42,
                account_id=100,
                request_id=request_id,
                metadata={"recovery_pending": False},
            )
            mock_session = _build_session_mock(
                scalar_returns=[100, _make_account(account_id=100), reservation_entry, None],
            )
            service = BillingService(_build_session_factory(mock_session))

            await service.settle_request(
                reservation_id=42,
                idempotency_key=f"settle-none-{uuid4().hex[:8]}",
                model=model,
                usage=usage,
            )

        mock_get.assert_called_once_with(model, None)
        mock_calc.assert_any_call(
            model,
            usage,
            model_multiplier=Decimal("1.50"),
            provider_multiplier=Decimal("1.00"),
        )
        assert mock_calc.call_count == 2

    async def test_both_multipliers_applied_multiplicatively(self) -> None:
        """Both model and provider multipliers applied in settle."""
        model = _make_model(price_multiplier=Decimal("1.50"))
        provider = _make_provider(public_multiplier=Decimal("2.00"))
        usage = CanonicalUsage(1000, 500)
        request_id = str(uuid4())

        with (
            patch(
                "ai_gateway.billing.service.calculate_cost",
                return_value=Decimal("0.30000000"),
            ) as mock_calc,
            patch(
                "ai_gateway.billing.service.get_effective_multipliers",
                return_value=(Decimal("1.50"), Decimal("2.00"), Decimal("0.80")),
            ) as mock_get,
        ):
            reservation_entry = _make_ledger_entry(
                entry_id=42,
                account_id=100,
                request_id=request_id,
                metadata={"recovery_pending": False},
            )
            mock_session = _build_session_mock(
                scalar_returns=[100, _make_account(account_id=100), reservation_entry, None],
            )
            service = BillingService(_build_session_factory(mock_session))

            await service.settle_request(
                reservation_id=42,
                idempotency_key=f"settle-both-{uuid4().hex[:8]}",
                model=model,
                usage=usage,
                provider=provider,
            )

        mock_get.assert_called_once_with(model, provider)
        mock_calc.assert_any_call(
            model,
            usage,
            model_multiplier=Decimal("1.50"),
            provider_multiplier=Decimal("2.00"),
        )
        mock_calc.assert_any_call(
            model,
            usage,
            model_multiplier=Decimal("1.50"),
            provider_multiplier=Decimal("0.80"),
        )
        assert mock_calc.call_count == 2


# ---------------------------------------------------------------------------
# _settlement_cost multiplier tests
# ---------------------------------------------------------------------------


class TestSettlementCostHelper:
    """Verify _settlement_cost helper handles provider multiplier."""

    def test_public_charge_and_platform_cost_use_independent_multipliers(self) -> None:
        model = Model(
            canonical_name="dual-priced-model",
            display_name="Dual priced model",
            input_price_per_million=Decimal("10.00"),
            output_price_per_million=Decimal("0"),
            price_multiplier=Decimal("1.50"),
        )
        provider = Provider(
            name="dual-priced-provider",
            credential_encrypted=b"fake",
            public_multiplier=Decimal("2.00"),
            cost_multiplier=Decimal("0.80"),
        )

        assert _settlement_costs(
            model=model,
            usage=CanonicalUsage(1_000_000, 0),
            cost=None,
            cost_amount=None,
            provider=provider,
        ) == (Decimal("30.00000000"), Decimal("12.00000000"))

    def test_settlement_cost_with_provider_multiplier(self) -> None:
        """_settlement_cost should pass provider to calculate_cost."""
        model = _make_model()
        provider = _make_provider(public_multiplier=Decimal("2.00"))
        usage = CanonicalUsage(1000, 500)

        with (
            patch(
                "ai_gateway.billing.service.calculate_cost",
                return_value=Decimal("0.20000000"),
            ) as mock_calc,
            patch(
                "ai_gateway.billing.service.get_effective_multipliers",
                return_value=(Decimal("1.50"), Decimal("2.00"), Decimal("0.80")),
            ) as mock_get,
        ):
            result = _settlement_cost(model=model, usage=usage, cost=None, provider=provider)

        mock_get.assert_called_once_with(model, provider)
        mock_calc.assert_any_call(
            model,
            usage,
            model_multiplier=Decimal("1.50"),
            provider_multiplier=Decimal("2.00"),
        )
        assert mock_calc.call_count == 2
        assert result == Decimal("0.20000000")

    def test_settlement_cost_with_no_provider(self) -> None:
        """_settlement_cost defaults provider_multiplier to 1.00 when provider is None."""
        model = _make_model()
        usage = CanonicalUsage(1000, 500)

        with (
            patch(
                "ai_gateway.billing.service.calculate_cost",
                return_value=Decimal("0.15000000"),
            ) as mock_calc,
            patch(
                "ai_gateway.billing.service.get_effective_multipliers",
                return_value=(Decimal("1.50"), Decimal("1.00"), Decimal("1.00")),
            ) as mock_get,
        ):
            result = _settlement_cost(model=model, usage=usage, cost=None, provider=None)

        mock_get.assert_called_once_with(model, None)
        mock_calc.assert_any_call(
            model,
            usage,
            model_multiplier=Decimal("1.50"),
            provider_multiplier=Decimal("1.00"),
        )
        assert mock_calc.call_count == 2
        assert result == Decimal("0.15000000")

    def test_settlement_cost_ignores_multipliers_when_cost_provided(self) -> None:
        """When cost is provided directly, multipliers are not applied."""
        provider = _make_provider()

        with (
            patch("ai_gateway.billing.service.calculate_cost") as mock_calc,
            patch("ai_gateway.billing.service.get_effective_multipliers") as mock_get,
        ):
            result = _settlement_cost(
                model=None, usage=None, cost=Decimal("0.50000000"), provider=provider
            )

        mock_calc.assert_not_called()
        mock_get.assert_not_called()
        assert result == Decimal("0.50000000")

    def test_settlement_cost_rejects_model_with_cost(self) -> None:
        """Providing both model and cost should raise TypeError."""
        model = _make_model()
        provider = _make_provider()

        with pytest.raises(TypeError, match="model cannot be provided with cost"):
            _settlement_cost(
                model=model,
                usage=None,
                cost=Decimal("0.50000000"),
                provider=provider,
            )


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Existing callers without provider should continue to work."""

    @patch("ai_gateway.billing.service._locked_account_for_user", new_callable=AsyncMock)
    @patch("ai_gateway.billing.service.get_effective_multipliers")
    @patch("ai_gateway.billing.service.calculate_cost")
    async def test_reserve_without_provider_still_works(
        self,
        mock_calculate_cost: MagicMock,
        mock_get_multipliers: MagicMock,
        mock_locked_account: AsyncMock,
    ) -> None:
        """reserve_balance without provider should default multipliers to 1.00."""
        model = _make_model(price_multiplier=Decimal("1.00"))
        mock_calculate_cost.return_value = Decimal("0.05000000")
        mock_get_multipliers.return_value = (
            Decimal("1.00"),
            Decimal("1.00"),
            Decimal("1.00"),
        )
        mock_locked_account.return_value = _make_account()
        mock_session = _build_session_mock(scalar_returns=[None, None])
        service = BillingService(_build_session_factory(mock_session))

        result = await service.reserve_balance(
            user_id=1,
            model=model,
            estimated_input_tokens=1000,
            max_output_tokens=500,
            idempotency_key=f"backward-{uuid4().hex[:8]}",
        )

        mock_get_multipliers.assert_called_once_with(model, None)
        mock_calculate_cost.assert_called_once_with(
            model,
            CanonicalUsage(1000, 500),
            model_multiplier=Decimal("1.00"),
            provider_multiplier=Decimal("1.00"),
        )
        assert isinstance(result, BalanceReservation)

    async def test_settle_without_provider_still_works(self) -> None:
        """settle_request without provider should default provider_multiplier to 1.00."""
        model = _make_model(price_multiplier=Decimal("1.00"))
        usage = CanonicalUsage(1000, 500)
        request_id = str(uuid4())

        with (
            patch(
                "ai_gateway.billing.service.calculate_cost",
                return_value=Decimal("0.05000000"),
            ) as mock_calc,
            patch(
                "ai_gateway.billing.service.get_effective_multipliers",
                return_value=(Decimal("1.00"), Decimal("1.00"), Decimal("1.00")),
            ) as mock_get,
        ):
            reservation_entry = _make_ledger_entry(
                entry_id=42,
                account_id=100,
                request_id=request_id,
                metadata={"recovery_pending": False},
            )
            mock_session = _build_session_mock(
                scalar_returns=[100, _make_account(account_id=100), reservation_entry, None],
            )
            service = BillingService(_build_session_factory(mock_session))

            result = await service.settle_request(
                reservation_id=42,
                idempotency_key=f"backward-{uuid4().hex[:8]}",
                model=model,
                usage=usage,
            )

        mock_get.assert_called_once_with(model, None)
        mock_calc.assert_any_call(
            model,
            usage,
            model_multiplier=Decimal("1.00"),
            provider_multiplier=Decimal("1.00"),
        )
        assert mock_calc.call_count == 2
        assert isinstance(result, SettlementResult)

    def test_recovered_model_without_price_multiplier_defaults_to_one(self) -> None:
        """_RecoveredModel (no price_multiplier) should default to Decimal('1.00').

        The orphan-recovery path builds a lightweight _RecoveredModel that
        stores only pricing fields; get_effective_multipliers must not raise
        AttributeError when it encounters such a stub.
        """
        from dataclasses import dataclass

        @dataclass
        class _RecoveredModelStub:
            canonical_name: str
            input_price_per_million: Decimal
            output_price_per_million: Decimal

        recovered = _RecoveredModelStub(
            "recovered-model",
            Decimal("10.00000000"),
            Decimal("20.00000000"),
        )

        with patch(
            "ai_gateway.billing.service.get_effective_multipliers",
            return_value=(Decimal("1.00"), Decimal("1.00"), Decimal("1.00")),
        ) as mock_get:
            result = _settlement_cost(
                model=recovered,
                usage=CanonicalUsage(1000, 500),
                cost=None,
                provider=None,
            )

        mock_get.assert_called_once_with(recovered, None)
        # base cost = (1000*10 + 500*20) / 1_000_000 = 0.02, multipliers both 1.00
        assert result == Decimal("0.02000000")


class TestCacheRecoveryMetadata:
    def test_recovery_round_trips_public_charge_and_platform_cost(self) -> None:
        recovery = ReservationRecovery(
            settlement_key="dual-cost-recovery",
            usage=CanonicalUsage(10, 5),
            usage_source=UsageSource.PROVIDER,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            cost=Decimal("30.00000000"),
            cost_amount=Decimal("12.00000000"),
        )

        restored = _reservation_recovery(_recovery_metadata(recovery))

        assert restored is not None
        assert restored.cost == Decimal("30.00000000")
        assert restored.cost_amount == Decimal("12.00000000")

    def test_recovery_usage_round_trips_cache_buckets(self) -> None:
        recovery = ReservationRecovery(
            settlement_key="cache-recovery",
            usage=CanonicalUsage(10, 5, 7, 3),
            usage_source=UsageSource.PROVIDER,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

        metadata = _recovery_metadata(recovery)
        restored = _reservation_recovery(metadata)

        assert metadata["recovery_cache_read_tokens"] == 7
        assert metadata["recovery_cache_write_tokens"] == 3
        assert restored is not None
        assert restored.usage == CanonicalUsage(10, 5, 7, 3)

    def test_legacy_recovery_metadata_defaults_cache_buckets_to_zero(self) -> None:
        metadata = {
            "recovery_pending": True,
            "recovery_settlement_key": "legacy-recovery",
            "recovery_input_tokens": 10,
            "recovery_output_tokens": 5,
            "recovery_usage_source": UsageSource.PROVIDER.value,
            "recovery_expires_at": datetime.now(UTC).isoformat(),
            "recovery_version": 1,
            "recovery_cost": None,
        }

        restored = _reservation_recovery(metadata)

        assert restored is not None
        assert restored.usage == CanonicalUsage(10, 5, 0, 0)

    def test_reservation_fingerprint_includes_cache_prices(self) -> None:
        first = _make_model(price_multiplier=Decimal("1.00"))
        second = _make_model(price_multiplier=Decimal("1.00"))
        second.cache_read_price_per_million = Decimal("6.00000000")

        first_fingerprint = _reservation_fingerprint(
            account_id=1,
            user_id=2,
            request_id="request",
            model=first,
            estimated_input_tokens=10,
            max_output_tokens=5,
            reserved_amount=Decimal("0.1"),
        )
        second_fingerprint = _reservation_fingerprint(
            account_id=1,
            user_id=2,
            request_id="request",
            model=second,
            estimated_input_tokens=10,
            max_output_tokens=5,
            reserved_amount=Decimal("0.1"),
        )

        assert first_fingerprint != second_fingerprint

    def test_settlement_fingerprint_includes_cache_usage(self) -> None:
        first = _settlement_fingerprint(
            reservation_id=1,
            actual_cost=Decimal("0.1"),
            usage=CanonicalUsage(10, 5, 7, 3),
            usage_source=UsageSource.PROVIDER,
        )
        second = _settlement_fingerprint(
            reservation_id=1,
            actual_cost=Decimal("0.1"),
            usage=CanonicalUsage(10, 5, 8, 2),
            usage_source=UsageSource.PROVIDER,
        )

        assert first != second


# ---------------------------------------------------------------------------
# Module-level wrapper tests
# ---------------------------------------------------------------------------


class TestModuleLevelWrappers:
    """Verify module-level reserve_balance/settle_request pass provider through."""

    async def test_module_reserve_passes_provider(self) -> None:
        """reserve_balance wrapper should forward provider to BillingService."""
        model = _make_model()
        provider = _make_provider()

        with patch("ai_gateway.billing.service.BillingService") as MockService:
            mock_instance = MockService.return_value
            mock_reservation = BalanceReservation(
                ledger_entry_id=1,
                account_id=100,
                user_id=1,
                request_id=str(uuid4()),
                idempotency_key="key",
                amount=Decimal("0.10000000"),
                balance_after=Decimal("999.90000000"),
            )
            mock_instance.reserve_balance = AsyncMock(return_value=mock_reservation)

            mock_session = AsyncMock()
            await module_reserve_balance(
                mock_session,
                user_id=1,
                model=model,
                estimated_input_tokens=1000,
                max_output_tokens=500,
                idempotency_key="module-reserve-key",
                provider=provider,
            )

            mock_instance.reserve_balance.assert_called_once()
            call_kwargs = mock_instance.reserve_balance.call_args.kwargs
            assert call_kwargs["provider"] is provider

    async def test_module_settle_passes_provider(self) -> None:
        """settle_request wrapper should forward provider to BillingService."""
        model = _make_model()
        provider = _make_provider()

        with patch("ai_gateway.billing.service.BillingService") as MockService:
            mock_instance = MockService.return_value
            mock_settlement = SettlementResult(
                account_id=100,
                request_id=str(uuid4()),
                reserved_amount=Decimal("0.10000000"),
                actual_cost=Decimal("0.08000000"),
                charged_amount=Decimal("0.08000000"),
                balance=Decimal("999.92000000"),
                total_spent=Decimal("0.08000000"),
                exhausted=False,
            )
            mock_instance.settle_request = AsyncMock(return_value=mock_settlement)

            mock_session = AsyncMock()
            await module_settle_request(
                mock_session,
                reservation_id=42,
                idempotency_key="module-settle-key",
                model=model,
                usage=CanonicalUsage(1000, 500),
                provider=provider,
            )

            mock_instance.settle_request.assert_called_once()
            call_kwargs = mock_instance.settle_request.call_args.kwargs
            assert call_kwargs["provider"] is provider
