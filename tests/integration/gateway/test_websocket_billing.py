from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest

from ai_gateway.billing.pricing import calculate_cost
from ai_gateway.billing.service import (
    AdjustmentResult,
    BalanceReservation,
    InsufficientBalance,
    SettlementResult,
)
from ai_gateway.core.enums import Protocol, UsageSource
from ai_gateway.gateway.websocket import WebSocketBillingCycle, WebSocketUsage, _usage_delta
from ai_gateway.protocols.types import CanonicalUsage


@dataclass
class FakeBilling:
    reservations: list[dict[str, Any]] = field(default_factory=list)
    settlements: list[dict[str, Any]] = field(default_factory=list)
    reservation_amount: Decimal = Decimal("1")
    fail_reservation_number: int | None = None
    fail_settlements_remaining: int = 0
    recovery_updates: list[dict[str, Any]] = field(default_factory=list)
    reconciliations: list[dict[str, Any]] = field(default_factory=list)

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


def test_openai_usage_normalizes_cache_reads_and_writes() -> None:
    usage = WebSocketUsage(Protocol.OPENAI)
    usage.observe_upstream(
        '{"type":"response.done","response":{"id":"r1","usage":'
        '{"input_tokens":100,"output_tokens":7,"input_tokens_details":'
        '{"cached_tokens":10,"cache_write_tokens":4}}}}'
    )

    assert usage.snapshot().usage == CanonicalUsage(86, 7, 10, 4)


def test_usage_delta_includes_cache_buckets() -> None:
    assert _usage_delta(
        CanonicalUsage(10, 5, 7, 3),
        CanonicalUsage(4, 2, 5, 1),
    ) == CanonicalUsage(6, 3, 2, 2)


def test_gemini_cumulative_usage_applies_positive_deltas_and_handles_counter_reset() -> None:
    usage = WebSocketUsage(Protocol.GEMINI)
    usage.observe_upstream('{"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":5}}')
    usage.observe_upstream('{"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":5}}')
    usage.observe_upstream('{"usageMetadata":{"promptTokenCount":15,"candidatesTokenCount":7}}')
    assert usage.snapshot().usage == CanonicalUsage(15, 7)

    usage.observe_upstream('{"usageMetadata":{"promptTokenCount":3,"candidatesTokenCount":2}}')
    assert usage.snapshot().usage == CanonicalUsage(18, 9)


def test_gemini_cumulative_usage_tracks_cached_content_separately() -> None:
    usage = WebSocketUsage(Protocol.GEMINI)
    usage.observe_upstream(
        '{"usageMetadata":{"promptTokenCount":100,"candidatesTokenCount":7,'
        '"cachedContentTokenCount":10}}'
    )
    usage.observe_upstream(
        '{"usageMetadata":{"promptTokenCount":120,"candidatesTokenCount":9,'
        '"cachedContentTokenCount":30}}'
    )

    assert usage.snapshot().usage == CanonicalUsage(90, 9, 30)

    usage.observe_upstream(
        '{"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":1,'
        '"cachedContentTokenCount":2}}'
    )
    assert usage.snapshot().usage == CanonicalUsage(98, 10, 32)


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
    await cycle.commit_frame("client", '{"text":"a"}')

    with pytest.raises(InsufficientBalance):
        await cycle.authorize_frame("client", '{"text":"many tokens beyond the window"}')

    assert len(billing.settlements) == 1
    assert billing.settlements[0]["usage"] == CanonicalUsage(1, 0)
    assert usage.snapshot().usage == CanonicalUsage(1, 0)
    assert cycle.has_open_reservation is False


@pytest.mark.asyncio
async def test_client_authorization_does_not_commit_usage_or_recovery() -> None:
    billing = FakeBilling()
    usage = WebSocketUsage(Protocol.OPENAI)
    cycle = WebSocketBillingCycle(
        billing=billing,  # type: ignore[arg-type]
        user_id=7,
        model=PricedModel(),  # type: ignore[arg-type]
        billing_key="websocket:client-commit",
        usage=usage,
        max_output_tokens=2,
    )
    frame = '{"text":"a"}'
    await cycle.reserve_initial(estimated_input_tokens=0)

    await cycle.authorize_frame("client", frame)

    assert usage.snapshot().usage == CanonicalUsage(0, 0)
    assert billing.recovery_updates == []

    await cycle.commit_frame("client", frame)

    assert usage.snapshot().usage == CanonicalUsage(1, 0)
    assert billing.recovery_updates == []

    await cycle.finalize()

    assert billing.recovery_updates[-1]["recovery"].usage == CanonicalUsage(1, 0)


@pytest.mark.asyncio
async def test_many_websocket_frames_share_one_final_recovery_checkpoint() -> None:
    billing = FakeBilling()
    usage = WebSocketUsage(Protocol.OPENAI)
    cycle = WebSocketBillingCycle(
        billing=billing,  # type: ignore[arg-type]
        user_id=7,
        model=PricedModel(),  # type: ignore[arg-type]
        billing_key="websocket:bounded-recovery",
        usage=usage,
        max_output_tokens=1000,
        token_threshold=100_000,
        interval_seconds=60,
    )
    await cycle.reserve_initial(estimated_input_tokens=0)

    for index in range(100):
        await cycle.commit_frame("client", f'{{"text":"frame-{index}"}}')

    assert billing.recovery_updates == []

    final_usage = usage.snapshot().usage
    await cycle.finalize()

    assert len(billing.recovery_updates) == 1
    assert billing.recovery_updates[0]["recovery"].usage == final_usage


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


@pytest.mark.asyncio
async def test_upstream_incurred_frame_is_settled_before_low_balance_closes() -> None:
    billing = FakeBilling(
        reservation_amount=Decimal("0.00000200"),
        fail_reservation_number=2,
    )
    usage = WebSocketUsage(Protocol.OPENAI)
    cycle = WebSocketBillingCycle(
        billing=billing,  # type: ignore[arg-type]
        user_id=7,
        model=PricedModel(),  # type: ignore[arg-type]
        billing_key="websocket:incurred",
        usage=usage,
        max_output_tokens=1,
    )
    await cycle.reserve_initial(estimated_input_tokens=0)
    frame = '{"text":"this provider output is already incurred and must be charged"}'

    with pytest.raises(InsufficientBalance):
        await cycle.authorize_frame("upstream", frame)

    incurred = usage.snapshot().usage
    assert incurred.output_tokens > 0
    assert billing.settlements[-1]["usage"] == incurred
    assert billing.recovery_updates[-1]["recovery"].usage == incurred
    assert cycle.actual_cost == calculate_cost(PricedModel(), incurred)
    assert cycle.uncollected_cost > 0
    assert cycle.has_open_reservation is False


@pytest.mark.asyncio
async def test_lower_native_usage_reconciles_estimated_checkpoint_once() -> None:
    billing = FakeBilling(reservation_amount=Decimal("0.00000500"))
    usage = WebSocketUsage(Protocol.OPENAI)
    model = PricedModel()
    cycle = WebSocketBillingCycle(
        billing=billing,  # type: ignore[arg-type]
        user_id=7,
        model=model,  # type: ignore[arg-type]
        billing_key="websocket:reconcile",
        usage=usage,
        max_output_tokens=1,
    )
    await cycle.reserve_initial(estimated_input_tokens=0)
    usage.observe_upstream('{"text":"one two three four five six seven eight"}')
    estimated = usage.snapshot().usage
    assert calculate_cost(model, estimated) > billing.reservation_amount
    assert await cycle.checkpoint(force_time=True) is True

    native_frame = (
        '{"type":"response.done","response":{"id":"r1","usage":'
        '{"input_tokens":0,"output_tokens":1}}}'
    )
    await cycle.authorize_frame("upstream", native_frame)
    await cycle.authorize_frame("upstream", native_frame)

    native_cost = calculate_cost(model, CanonicalUsage(0, 1))
    expected_refund = billing.reservation_amount - native_cost
    assert [call["amount"] for call in billing.reconciliations] == [expected_refund]
    assert cycle.actual_cost == native_cost
    assert cycle.charged_cost == native_cost
    assert cycle.reported_uncollected_cost == 0


@pytest.mark.asyncio
async def test_higher_later_native_usage_is_charged_as_authorized_delta() -> None:
    billing = FakeBilling(reservation_amount=Decimal("0.00000500"))
    usage = WebSocketUsage(Protocol.OPENAI)
    cycle = WebSocketBillingCycle(
        billing=billing,  # type: ignore[arg-type]
        user_id=7,
        model=PricedModel(),  # type: ignore[arg-type]
        billing_key="websocket:native-increase",
        usage=usage,
        max_output_tokens=1,
    )
    await cycle.reserve_initial(estimated_input_tokens=0)
    await cycle.authorize_frame(
        "upstream",
        '{"response":{"id":"r1","usage":{"input_tokens":0,"output_tokens":1}}}',
    )
    assert await cycle.checkpoint(force_time=True) is True

    await cycle.authorize_frame(
        "upstream",
        '{"response":{"id":"r2","usage":{"input_tokens":0,"output_tokens":10}}}',
    )

    assert billing.settlements[-1]["usage"] == CanonicalUsage(0, 10)
    assert len(billing.reservations) == 3


@pytest.mark.asyncio
async def test_mixed_usage_dimensions_reconcile_by_cumulative_cost() -> None:
    billing = FakeBilling()
    usage = WebSocketUsage(Protocol.OPENAI)
    model = PricedModel()
    cycle = WebSocketBillingCycle(
        billing=billing,  # type: ignore[arg-type]
        user_id=7,
        model=model,  # type: ignore[arg-type]
        billing_key="websocket:mixed-money",
        usage=usage,
        max_output_tokens=1,
    )
    await cycle.reserve_initial(estimated_input_tokens=0)
    for _ in range(10):
        usage.observe_client('{"text":"a"}')
        usage.observe_upstream('{"text":"a"}')
    assert usage.snapshot().usage == CanonicalUsage(10, 10)
    assert await cycle.checkpoint(force_time=True) is True

    native = (
        '{"type":"response.done","response":{"id":"mixed-1","usage":'
        '{"input_tokens":5,"output_tokens":15}}}'
    )
    await cycle.authorize_frame("upstream", native)
    assert await cycle.checkpoint(force_time=True) is True
    await cycle.authorize_frame("upstream", native)
    await cycle.finalize()

    assert [call["cost"] for call in billing.settlements[:2]] == [
        Decimal("0.00003000"),
        Decimal("0.00000500"),
    ]
    assert sum(result["cost"] for result in billing.settlements) == Decimal("0.00003500")
    assert billing.reconciliations == []
    assert cycle.actual_cost == Decimal("0.00003500")
    assert cycle.charged_cost == Decimal("0.00003500")


@pytest.mark.asyncio
async def test_mixed_usage_dimensions_refund_exact_monetary_difference_once() -> None:
    billing = FakeBilling()
    usage = WebSocketUsage(Protocol.OPENAI)
    cycle = WebSocketBillingCycle(
        billing=billing,  # type: ignore[arg-type]
        user_id=7,
        model=PricedModel(),  # type: ignore[arg-type]
        billing_key="websocket:mixed-refund",
        usage=usage,
        max_output_tokens=1,
    )
    await cycle.reserve_initial(estimated_input_tokens=0)
    for _ in range(10):
        usage.observe_client('{"text":"a"}')
        usage.observe_upstream('{"text":"a"}')
    assert await cycle.checkpoint(force_time=True) is True

    native = (
        '{"type":"response.done","response":{"id":"mixed-lower","usage":'
        '{"input_tokens":15,"output_tokens":5}}}'
    )
    await cycle.authorize_frame("upstream", native)
    await cycle.authorize_frame("upstream", native)

    assert [call["amount"] for call in billing.reconciliations] == [Decimal("0.00000500")]
    assert cycle.actual_cost == Decimal("0.00002500")
    assert cycle.charged_cost == Decimal("0.00002500")
