"""Test that WebSocket gateway passes provider to billing service."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ai_gateway.billing.pricing import calculate_cost
from ai_gateway.billing.service import (
    AdjustmentResult,
    BalanceReservation,
    InsufficientBalance,
    SettlementResult,
)
from ai_gateway.core.enums import Protocol, UsageSource
from ai_gateway.db.models import Provider
from ai_gateway.gateway.websocket import WebSocketBillingCycle, WebSocketUsage
from ai_gateway.protocols.types import CanonicalUsage


@dataclass
class _PricedModel:
    canonical_name: str = "ws-test-model"
    input_price_per_million: Decimal = Decimal("1")
    output_price_per_million: Decimal = Decimal("2")


@dataclass
class FakeBillingWithProvider:
    """Fake billing backend that records provider arguments."""

    reservations: list[dict[str, Any]] = field(default_factory=list)
    settlements: list[dict[str, Any]] = field(default_factory=list)
    reservation_amount: Decimal = Decimal("1")
    recovery_updates: list[dict[str, Any]] = field(default_factory=list)
    reconciliations: list[dict[str, Any]] = field(default_factory=list)

    async def reserve_balance(self, **kwargs: Any) -> BalanceReservation:
        self.reservations.append(kwargs)
        sequence = len(self.reservations)
        return BalanceReservation(
            sequence,
            1,
            kwargs["user_id"],
            f"request-{sequence}",
            kwargs["idempotency_key"],
            self.reservation_amount,
            Decimal("9"),
        )

    async def settle_request(self, **kwargs: Any) -> SettlementResult:
        self.settlements.append(kwargs)
        actual_cost = (
            calculate_cost(kwargs["model"], kwargs["usage"])
            if kwargs.get("model") is not None
            else Decimal(str(kwargs.get("cost", "0")))
        )
        charged = min(actual_cost, self.reservation_amount)
        return SettlementResult(
            1,
            f"request-{len(self.settlements)}",
            self.reservation_amount,
            actual_cost,
            charged,
            Decimal("9"),
            charged,
            False,
            actual_cost - charged,
        )

    async def update_reservation_recovery(self, **kwargs: Any) -> bool:
        self.recovery_updates.append(kwargs)
        return True

    async def reconcile_charge(self, **kwargs: Any) -> AdjustmentResult:
        self.reconciliations.append(kwargs)
        return AdjustmentResult(
            len(self.reconciliations),
            1,
            kwargs["amount"],
            Decimal("9"),
            Decimal("0"),
        )


class TestWebSocketProviderIntegration:
    """Test that WebSocket gateway passes provider to billing service."""

    @pytest.mark.asyncio
    async def test_settle_request_receives_provider(self) -> None:
        """Verify settle_request is called with provider parameter."""
        billing = FakeBillingWithProvider()
        usage = WebSocketUsage(Protocol.OPENAI)
        provider = Provider(
            id=42,
            name="ws-test-provider",
            credential_encrypted=b"enc",
            price_multiplier=Decimal("2.00"),
        )
        cycle = WebSocketBillingCycle(
            billing=billing,  # type: ignore[arg-type]
            user_id=7,
            model=_PricedModel(),  # type: ignore[arg-type]
            billing_key="websocket:provider-test",
            usage=usage,
            max_output_tokens=8,
            token_threshold=100_000,
            interval_seconds=60,
            provider=provider,
        )

        await cycle.reserve_initial(estimated_input_tokens=3)
        usage.observe_upstream(
            '{"type":"response.done","response":{"id":"r1","usage":'
            '{"input_tokens":60000,"output_tokens":40000}}}'
        )
        assert await cycle.checkpoint() is True

        assert len(billing.settlements) >= 1
        for settlement_call in billing.settlements:
            assert "provider" in settlement_call, (
                "settle_request must receive provider parameter"
            )
            assert settlement_call["provider"] is provider

    @pytest.mark.asyncio
    async def test_provider_loaded_at_connection_start(self) -> None:
        """Verify provider is accepted when billing cycle is created."""
        billing = FakeBillingWithProvider()
        usage = WebSocketUsage(Protocol.OPENAI)
        provider = Provider(
            id=10,
            name="connection-provider",
            credential_encrypted=b"enc",
            price_multiplier=Decimal("1.50"),
        )

        cycle = WebSocketBillingCycle(
            billing=billing,  # type: ignore[arg-type]
            user_id=3,
            model=_PricedModel(),  # type: ignore[arg-type]
            billing_key="websocket:conn-test",
            usage=usage,
            max_output_tokens=8,
            provider=provider,
        )

        await cycle.reserve_initial(estimated_input_tokens=0)
        # Provider was passed at construction (connection start)
        # and is used for subsequent billing operations
        usage.observe_upstream(
            '{"type":"response.done","response":{"id":"r1","usage":'
            '{"input_tokens":5,"output_tokens":3}}}'
        )
        await cycle.finalize()

        assert len(billing.settlements) >= 1
        assert billing.settlements[0]["provider"] is provider

    @pytest.mark.asyncio
    async def test_same_provider_used_across_checkpoints(self) -> None:
        """Verify same provider is used for multiple billing checkpoints."""
        billing = FakeBillingWithProvider()
        usage = WebSocketUsage(Protocol.OPENAI)
        provider = Provider(
            id=99,
            name="multi-checkpoint-provider",
            credential_encrypted=b"enc",
            price_multiplier=Decimal("3.00"),
        )
        cycle = WebSocketBillingCycle(
            billing=billing,  # type: ignore[arg-type]
            user_id=7,
            model=_PricedModel(),  # type: ignore[arg-type]
            billing_key="websocket:multi-checkpoint",
            usage=usage,
            max_output_tokens=8,
            token_threshold=100_000,
            interval_seconds=60,
            provider=provider,
        )

        await cycle.reserve_initial(estimated_input_tokens=3)

        # First checkpoint
        usage.observe_upstream(
            '{"type":"response.done","response":{"id":"r1","usage":'
            '{"input_tokens":60000,"output_tokens":40000}}}'
        )
        assert await cycle.checkpoint() is True

        # Second checkpoint
        usage.observe_upstream(
            '{"type":"response.done","response":{"id":"r2","usage":'
            '{"input_tokens":60000,"output_tokens":40000}}}'
        )
        assert await cycle.checkpoint() is True

        # Finalize (triggers third settlement)
        await cycle.finalize()

        # All settlements should use the same provider
        assert len(billing.settlements) >= 2
        for settlement_call in billing.settlements:
            assert settlement_call["provider"] is provider

    @pytest.mark.asyncio
    async def test_settle_request_without_provider_still_works(self) -> None:
        """Verify backward compatibility: billing cycle works when no provider is given."""
        billing = FakeBillingWithProvider()
        usage = WebSocketUsage(Protocol.OPENAI)
        cycle = WebSocketBillingCycle(
            billing=billing,  # type: ignore[arg-type]
            user_id=7,
            model=_PricedModel(),  # type: ignore[arg-type]
            billing_key="websocket:no-provider",
            usage=usage,
            max_output_tokens=8,
        )

        await cycle.reserve_initial(estimated_input_tokens=3)
        usage.observe_upstream(
            '{"type":"response.done","response":{"id":"r1","usage":'
            '{"input_tokens":5,"output_tokens":3}}}'
        )
        await cycle.finalize()

        assert len(billing.settlements) >= 1
        # When no provider is given, settle_request should receive provider=None
        assert billing.settlements[0].get("provider") is None
