from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest

from ai_gateway.billing.service import BalanceReservation, SettlementResult
from ai_gateway.core.enums import Protocol, UsageSource
from ai_gateway.gateway.websocket import WebSocketBillingCycle, WebSocketUsage
from ai_gateway.protocols.types import CanonicalUsage


@dataclass
class FakeBilling:
    reservations: list[dict[str, Any]] = field(default_factory=list)
    settlements: list[dict[str, Any]] = field(default_factory=list)

    async def reserve_balance(self, **kwargs: Any) -> BalanceReservation:
        self.reservations.append(kwargs)
        sequence = len(self.reservations)
        return BalanceReservation(
            sequence,
            1,
            kwargs["user_id"],
            f"request-{sequence}",
            kwargs["idempotency_key"],
            Decimal("1"),
            Decimal("9"),
        )

    async def settle_request(self, **kwargs: Any) -> SettlementResult:
        self.settlements.append(kwargs)
        return SettlementResult(
            1,
            f"request-{len(self.settlements)}",
            Decimal("1"),
            Decimal("0.1"),
            Decimal("0.1"),
            Decimal("9"),
            Decimal("0.1"),
            False,
        )


@dataclass
class PricedModel:
    canonical_name: str = "realtime-model"
    input_price_per_million: Decimal = Decimal("1")
    output_price_per_million: Decimal = Decimal("2")


@pytest.mark.asyncio
async def test_periodic_billing_settles_each_reservation_and_finalizes_without_leak() -> None:
    billing = FakeBilling()
    usage = WebSocketUsage(Protocol.OPENAI)
    cycle = WebSocketBillingCycle(
        billing=billing,  # type: ignore[arg-type]
        user_id=7,
        model=PricedModel(),  # type: ignore[arg-type]
        billing_key="websocket:test",
        usage=usage,
        max_output_tokens=8,
        token_threshold=100_000,
        interval_seconds=60,
    )

    await cycle.reserve_initial(estimated_input_tokens=3)
    usage.observe_upstream(
        '{"type":"response.done","response":{"usage":{"input_tokens":60000,"output_tokens":40000}}}'
    )
    assert await cycle.checkpoint() is True
    usage.observe_upstream('{"usage":{"prompt_tokens":120000,"completion_tokens":80000}}')
    assert await cycle.checkpoint() is True
    await cycle.finalize()
    await cycle.finalize()

    assert len(billing.reservations) == 3
    assert len(billing.settlements) == 3
    first_usage = billing.settlements[0]["usage"]
    second_usage = billing.settlements[1]["usage"]
    assert first_usage == CanonicalUsage(input_tokens=60000, output_tokens=40000)
    assert second_usage == CanonicalUsage(input_tokens=60000, output_tokens=40000)
    assert billing.settlements[0]["usage_source"] is UsageSource.PROVIDER
    assert cycle.has_open_reservation is False
