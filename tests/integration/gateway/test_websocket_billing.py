from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest

from ai_gateway.billing.service import (
    BalanceReservation,
    InsufficientBalance,
    SettlementResult,
)
from ai_gateway.core.enums import Protocol, UsageSource
from ai_gateway.gateway.websocket import WebSocketBillingCycle, WebSocketUsage
from ai_gateway.protocols.types import CanonicalUsage


@dataclass
class FakeBilling:
    reservations: list[dict[str, Any]] = field(default_factory=list)
    settlements: list[dict[str, Any]] = field(default_factory=list)
    reservation_amount: Decimal = Decimal("1")
    fail_reservation_number: int | None = None
    fail_settlements_remaining: int = 0

    async def reserve_balance(self, **kwargs: Any) -> BalanceReservation:
        self.reservations.append(kwargs)
        sequence = len(self.reservations)
        if sequence == self.fail_reservation_number:
            raise InsufficientBalance(required=Decimal("1"), available=Decimal("0"))
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
        if self.fail_settlements_remaining:
            self.fail_settlements_remaining -= 1
            raise RuntimeError("transient settlement failure")
        return SettlementResult(
            1,
            f"request-{len(self.settlements)}",
            self.reservation_amount,
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
        '{"type":"response.done","response":{"id":"r1","usage":'
        '{"input_tokens":60000,"output_tokens":40000}}}'
    )
    assert await cycle.checkpoint() is True
    usage.observe_upstream(
        '{"type":"response.done","response":{"id":"r2","usage":'
        '{"input_tokens":60000,"output_tokens":40000}}}'
    )
    assert await cycle.checkpoint() is True
    await cycle.finalize()
    await cycle.finalize()

    assert len(billing.reservations) == 3
    assert len(billing.settlements) == 3
    assert billing.settlements[0]["usage"] == CanonicalUsage(60000, 40000)
    assert billing.settlements[1]["usage"] == CanonicalUsage(60000, 40000)
    assert billing.settlements[0]["usage_source"] is UsageSource.PROVIDER
    assert cycle.has_open_reservation is False


def test_openai_usage_sums_responses_dedupes_and_retains_estimated_tail() -> None:
    usage = WebSocketUsage(Protocol.OPENAI)
    first = (
        '{"type":"response.done","response":{"id":"r1","usage":'
        '{"input_tokens":10,"output_tokens":5}}}'
    )
    second = (
        '{"type":"response.done","response":{"id":"r2","usage":'
        '{"input_tokens":7,"output_tokens":3}}}'
    )

    usage.observe_upstream(first)
    usage.observe_upstream(first)
    usage.observe_upstream(second)
    native = usage.snapshot()
    assert native.usage == CanonicalUsage(17, 8)
    assert native.usage_source is UsageSource.PROVIDER

    usage.observe_upstream('{"type":"response.output_text.delta","delta":"abrupt tail"}')
    tailed = usage.snapshot()
    assert tailed.usage.input_tokens == 17
    assert tailed.usage.output_tokens > 8
    assert tailed.usage_source is UsageSource.ESTIMATED


def test_gemini_cumulative_usage_applies_positive_deltas_and_handles_counter_reset() -> None:
    usage = WebSocketUsage(Protocol.GEMINI)
    usage.observe_upstream('{"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":5}}')
    usage.observe_upstream('{"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":5}}')
    usage.observe_upstream('{"usageMetadata":{"promptTokenCount":15,"candidatesTokenCount":7}}')
    assert usage.snapshot().usage == CanonicalUsage(15, 7)

    usage.observe_upstream('{"usageMetadata":{"promptTokenCount":3,"candidatesTokenCount":2}}')
    assert usage.snapshot().usage == CanonicalUsage(18, 9)


@pytest.mark.asyncio
async def test_authorization_checkpoints_before_frame_exceeds_reserved_cost() -> None:
    billing = FakeBilling(
        reservation_amount=Decimal("0.00000200"),
        fail_reservation_number=2,
    )
    usage = WebSocketUsage(Protocol.OPENAI)
    cycle = WebSocketBillingCycle(
        billing=billing,  # type: ignore[arg-type]
        user_id=7,
        model=PricedModel(),  # type: ignore[arg-type]
        billing_key="websocket:low-balance",
        usage=usage,
        max_output_tokens=2,
    )
    await cycle.reserve_initial(estimated_input_tokens=0)
    await cycle.authorize_frame("client", '{"text":"a"}')

    with pytest.raises(InsufficientBalance):
        await cycle.authorize_frame("client", '{"text":"many tokens beyond the window"}')

    assert len(billing.settlements) == 1
    assert billing.settlements[0]["usage"] == CanonicalUsage(1, 0)
    assert usage.snapshot().usage == CanonicalUsage(1, 0)
    assert cycle.has_open_reservation is False


@pytest.mark.asyncio
async def test_finalization_retries_transient_settlement_failure_and_releases_reservation() -> None:
    billing = FakeBilling(fail_settlements_remaining=1)
    usage = WebSocketUsage(Protocol.OPENAI)
    cycle = WebSocketBillingCycle(
        billing=billing,  # type: ignore[arg-type]
        user_id=7,
        model=PricedModel(),  # type: ignore[arg-type]
        billing_key="websocket:retry-finalize",
        usage=usage,
        max_output_tokens=8,
    )
    await cycle.reserve_initial(estimated_input_tokens=0)

    await cycle.finalize()

    assert len(billing.settlements) == 2
    assert cycle.has_open_reservation is False
