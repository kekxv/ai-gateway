from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import sha256
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import orjson
from fastapi import Request
from sqlalchemy import exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ai_gateway.billing.multipliers import get_effective_multipliers
from ai_gateway.billing.pricing import MONEY_QUANTUM, PricedModel, calculate_cost
from ai_gateway.core.enums import LedgerKind, UsageSource
from ai_gateway.core.errors import GatewayError
from ai_gateway.db.models import Account, LedgerEntry
from ai_gateway.protocols.types import CanonicalUsage
from ai_gateway.routing.sessions import mutation_session_factory_for

if TYPE_CHECKING:
    from ai_gateway.db.models import Provider

DEFAULT_MAX_OUTPUT_TOKENS = 4096
MAX_MONEY = Decimal("999999999999.99999999")
SessionFactory = Callable[[], AsyncSession]


class BillingError(GatewayError):
    """Base error for a balance mutation that cannot be completed."""


class BillingAmountOutOfRange(BillingError, ValueError):
    code = "billing_amount_out_of_range"
    status_code = 422

    def __init__(self, field: str = "billing value") -> None:
        super().__init__(f"{field} must fit DECIMAL(20,8) with at most 20 total digits")


class InsufficientBalance(BillingError):
    code = "insufficient_balance"
    status_code = 402

    def __init__(self, *, required: Decimal, available: Decimal) -> None:
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient balance: {available:.8f} available, {required:.8f} required"
        )


class AccountNotFound(BillingError):
    code = "account_not_found"
    status_code = 404

    def __init__(self) -> None:
        super().__init__("Billing account not found")


class ReservationNotFound(BillingError):
    code = "reservation_not_found"
    status_code = 404

    def __init__(self) -> None:
        super().__init__("Balance reservation not found")


class IdempotencyConflict(BillingError):
    code = "idempotency_conflict"
    status_code = 409

    def __init__(self) -> None:
        super().__init__("Idempotency key conflicts with an existing billing operation")


class _RecoveryClaimLost(Exception):
    pass


@dataclass(frozen=True, slots=True)
class BalanceReservation:
    ledger_entry_id: int
    account_id: int
    user_id: int
    request_id: str
    idempotency_key: str
    amount: Decimal
    balance_after: Decimal


@dataclass(frozen=True, slots=True)
class SettlementResult:
    account_id: int
    request_id: str
    reserved_amount: Decimal
    actual_cost: Decimal
    charged_amount: Decimal
    balance: Decimal
    total_spent: Decimal
    exhausted: bool
    uncollected_amount: Decimal = Decimal("0")
    cost_amount: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class AdjustmentResult:
    ledger_entry_id: int
    account_id: int
    amount: Decimal
    balance: Decimal
    total_spent: Decimal


@dataclass(frozen=True, slots=True)
class ReservationRecovery:
    settlement_key: str
    usage: CanonicalUsage
    usage_source: UsageSource
    expires_at: datetime
    cost: Decimal | None = None
    cost_amount: Decimal | None = None
    version: int = 0


@dataclass(slots=True)
class _RecoveredModel:
    canonical_name: str
    input_price_per_million: Decimal
    output_price_per_million: Decimal
    cache_read_price_per_million: Decimal = Decimal("0")
    cache_write_price_per_million: Decimal = Decimal("0")


class BillingService:
    """Execute each balance mutation in its own short-lived transaction."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        default_max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ) -> None:
        if default_max_output_tokens < 1:
            raise ValueError("default_max_output_tokens must be positive")
        self._session_factory = session_factory
        self.default_max_output_tokens = default_max_output_tokens

    async def reserve_balance(
        self,
        *,
        user_id: int,
        model: PricedModel,
        estimated_input_tokens: int,
        max_output_tokens: int | None,
        idempotency_key: str,
        request_id: UUID | str | None = None,
        recovery: ReservationRecovery | None = None,
        provider: Provider | None = None,
        provider_public_multiplier: Decimal | None = None,
    ) -> BalanceReservation:
        if estimated_input_tokens < 0:
            raise ValueError("estimated_input_tokens must be nonnegative")
        selected_max_output = (
            self.default_max_output_tokens if max_output_tokens is None else max_output_tokens
        )
        if selected_max_output < 0:
            raise ValueError("max_output_tokens must be nonnegative")
        normalized_key = _normalize_idempotency_key(idempotency_key)
        model_mult, public_mult, _ = get_effective_multipliers(model, provider)
        if provider_public_multiplier is not None:
            if provider_public_multiplier < 0:
                raise ValueError("provider_public_multiplier must be nonnegative")
            public_mult = provider_public_multiplier
        reserved_amount = calculate_cost(
            model,
            CanonicalUsage(estimated_input_tokens, selected_max_output),
            model_multiplier=model_mult,
            provider_multiplier=public_mult,
        )
        _validate_money_magnitude(reserved_amount, "reservation amount")

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    account = await _locked_account_for_user(session, user_id)
                    existing = await session.scalar(
                        select(LedgerEntry)
                        .where(LedgerEntry.idempotency_key == normalized_key)
                        .with_for_update()
                    )
                    if existing is not None:
                        effective_request_id = (
                            existing.request_id if request_id is None else str(request_id)
                        )
                        if effective_request_id is None:
                            raise IdempotencyConflict
                        fingerprint = _reservation_fingerprint(
                            account_id=account.id,
                            user_id=user_id,
                            request_id=effective_request_id,
                            model=model,
                            estimated_input_tokens=estimated_input_tokens,
                            max_output_tokens=selected_max_output,
                            reserved_amount=reserved_amount,
                            model_multiplier=model_mult,
                            public_multiplier=public_mult,
                        )
                        await _validate_reservation_replay(
                            session,
                            entry=existing,
                            account_id=account.id,
                            fingerprint=fingerprint,
                        )
                        return _reservation_from_entry(existing, user_id=user_id)
                    normalized_request_id = str(request_id or uuid4())
                    fingerprint = _reservation_fingerprint(
                        account_id=account.id,
                        user_id=user_id,
                        request_id=normalized_request_id,
                        model=model,
                        estimated_input_tokens=estimated_input_tokens,
                        max_output_tokens=selected_max_output,
                        reserved_amount=reserved_amount,
                        model_multiplier=model_mult,
                        public_multiplier=public_mult,
                    )
                    existing_request = await session.scalar(
                        select(LedgerEntry)
                        .where(
                            LedgerEntry.account_id == account.id,
                            LedgerEntry.request_id == normalized_request_id,
                            LedgerEntry.kind == LedgerKind.RESERVATION,
                        )
                        .with_for_update()
                    )
                    if existing_request is not None:
                        raise IdempotencyConflict
                    if account.balance < reserved_amount:
                        raise InsufficientBalance(
                            required=reserved_amount,
                            available=account.balance,
                        )

                    account.balance = _money(
                        account.balance - reserved_amount,
                        "reservation balance_after",
                    )
                    account.version += 1
                    metadata = {
                        "estimated_input_tokens": estimated_input_tokens,
                        "max_output_tokens": selected_max_output,
                        "model": _model_name(model),
                        "input_price_per_million": str(model.input_price_per_million),
                        "output_price_per_million": str(model.output_price_per_million),
                        "cache_read_price_per_million": str(_cache_read_price(model)),
                        "cache_write_price_per_million": str(_cache_write_price(model)),
                        "reserved_amount": str(reserved_amount),
                        "model_multiplier": str(model_mult),
                        "public_multiplier": str(public_mult),
                        "reservation_fingerprint": fingerprint,
                    }
                    if recovery is not None:
                        metadata.update(_recovery_metadata(recovery, version=1))
                    entry = LedgerEntry(
                        account_id=account.id,
                        request_id=normalized_request_id,
                        idempotency_key=normalized_key,
                        kind=LedgerKind.RESERVATION,
                        amount=-reserved_amount,
                        balance_after=account.balance,
                        metadata_json=metadata,
                    )
                    session.add(entry)
                    await session.flush()
                    return BalanceReservation(
                        ledger_entry_id=entry.id,
                        account_id=account.id,
                        user_id=user_id,
                        request_id=normalized_request_id,
                        idempotency_key=normalized_key,
                        amount=reserved_amount,
                        balance_after=account.balance,
                    )
        except IntegrityError as exc:
            raise IdempotencyConflict from exc

    async def settle_request(
        self,
        *,
        reservation_id: int,
        idempotency_key: str,
        model: PricedModel | None = None,
        usage: CanonicalUsage | None = None,
        cost: Decimal | None = None,
        cost_amount: Decimal | None = None,
        usage_source: UsageSource | None = None,
        expected_recovery_version: int | None = None,
        expected_recovery_claim: str | None = None,
        provider: Provider | None = None,
    ) -> SettlementResult:
        normalized_key = _normalize_idempotency_key(
            idempotency_key,
            suffix_length=max(len(":release"), len(":usage")),
        )
        actual_cost, platform_cost = _settlement_costs(
            model=model,
            usage=usage,
            cost=cost,
            cost_amount=cost_amount,
            provider=provider,
        )
        fingerprint = _settlement_fingerprint(
            reservation_id=reservation_id,
            actual_cost=actual_cost,
            cost_amount=platform_cost,
            usage=usage,
            usage_source=usage_source,
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    account_id = await session.scalar(
                        select(LedgerEntry.account_id).where(
                            LedgerEntry.id == reservation_id,
                            LedgerEntry.kind == LedgerKind.RESERVATION,
                        )
                    )
                    if account_id is None:
                        raise ReservationNotFound
                    account = await _locked_account(session, account_id)
                    reservation = await session.scalar(
                        select(LedgerEntry)
                        .where(
                            LedgerEntry.id == reservation_id,
                            LedgerEntry.kind == LedgerKind.RESERVATION,
                        )
                        .with_for_update()
                    )
                    if reservation is None or reservation.account_id != account_id:
                        raise ReservationNotFound
                    if reservation.request_id is None:
                        raise RuntimeError("reservation is missing its request ID")
                    if expected_recovery_version is not None:
                        metadata = reservation.metadata_json
                        if (
                            metadata.get("recovery_version") != expected_recovery_version
                            or metadata.get("recovery_claimed_version") != expected_recovery_version
                            or metadata.get("recovery_claim_token") != expected_recovery_claim
                        ):
                            raise _RecoveryClaimLost
                    release, usage_entry = await _settlement_entries(
                        session,
                        account_id=account.id,
                        request_id=reservation.request_id,
                    )
                    if release is not None or usage_entry is not None:
                        if release is None or usage_entry is None:
                            raise IdempotencyConflict
                        _validate_settlement_replay(
                            reservation=reservation,
                            release=release,
                            usage_entry=usage_entry,
                            settlement_key=normalized_key,
                            fingerprint=fingerprint,
                        )
                        return _settlement_from_entries(
                            reservation=reservation,
                            usage_entry=usage_entry,
                        )

                    expected_release_key = f"{normalized_key}:release"
                    expected_usage_key = f"{normalized_key}:usage"
                    conflicting_key = await session.scalar(
                        select(LedgerEntry)
                        .where(
                            or_(
                                LedgerEntry.idempotency_key == expected_release_key,
                                LedgerEntry.idempotency_key == expected_usage_key,
                            )
                        )
                        .with_for_update()
                    )
                    if conflicting_key is not None:
                        raise IdempotencyConflict

                    reserved_amount = _money(-reservation.amount)
                    balance_after_release = _money(
                        account.balance + reserved_amount,
                        "settlement release balance_after",
                    )
                    charged_amount = min(actual_cost, balance_after_release)
                    final_balance = _money(
                        balance_after_release - charged_amount,
                        "settlement balance_after",
                    )
                    total_spent = _money(
                        account.total_spent + charged_amount,
                        "settlement total_spent",
                    )
                    if final_balance < 0:
                        raise BillingAmountOutOfRange("settlement balance_after")
                    exhausted = final_balance == 0
                    uncollected = _money(actual_cost - charged_amount)
                    common_metadata: dict[str, Any] = {
                        "reservation_entry_id": reservation.id,
                        "request_id": reservation.request_id,
                        "settlement_key": normalized_key,
                        "settlement_fingerprint": fingerprint,
                    }
                    release = LedgerEntry(
                        account_id=account.id,
                        request_id=reservation.request_id,
                        idempotency_key=expected_release_key,
                        kind=LedgerKind.RESERVATION_RELEASE,
                        amount=reserved_amount,
                        balance_after=balance_after_release,
                        metadata_json=common_metadata,
                    )
                    usage_metadata = {
                        **common_metadata,
                        "actual_cost": str(actual_cost),
                        "cost_amount": str(platform_cost),
                        "charged_amount": str(charged_amount),
                        "uncollected_amount": str(uncollected),
                        "total_spent_after": str(total_spent),
                        "exhausted": exhausted,
                    }
                    if usage is not None:
                        usage_metadata.update(
                            input_tokens=usage.input_tokens,
                            output_tokens=usage.output_tokens,
                        )
                    if usage_source is not None:
                        usage_metadata["usage_source"] = usage_source.value
                    usage_entry = LedgerEntry(
                        account_id=account.id,
                        request_id=reservation.request_id,
                        idempotency_key=expected_usage_key,
                        kind=LedgerKind.USAGE,
                        amount=-charged_amount,
                        balance_after=final_balance,
                        metadata_json=usage_metadata,
                    )
                    account.balance = final_balance
                    account.total_spent = total_spent
                    account.version += 1
                    reservation.metadata_json = {
                        **reservation.metadata_json,
                        "recovery_pending": False,
                        "recovery_claimed_version": None,
                        "recovery_claim_token": None,
                        "recovery_claimed_at": None,
                    }
                    session.add_all((release, usage_entry))
                    await session.flush()
                    return SettlementResult(
                        account_id=account.id,
                        request_id=reservation.request_id,
                        reserved_amount=reserved_amount,
                        actual_cost=actual_cost,
                        charged_amount=charged_amount,
                        balance=final_balance,
                        total_spent=total_spent,
                        exhausted=exhausted,
                        uncollected_amount=uncollected,
                        cost_amount=platform_cost,
                    )
        except IntegrityError as exc:
            raise IdempotencyConflict from exc

    async def adjust_balance(
        self,
        *,
        user_id: int,
        amount: Decimal,
        reason: str,
        idempotency_key: str,
    ) -> AdjustmentResult:
        _validate_money_magnitude(amount, "adjustment amount")
        normalized_amount = _money(amount, "adjustment amount")
        if amount != normalized_amount:
            raise ValueError("adjustment amount has more than eight decimal places")
        if normalized_amount == 0:
            raise ValueError("adjustment amount must be nonzero")
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("adjustment reason is required")
        normalized_key = _normalize_idempotency_key(idempotency_key)

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    account = await _locked_account_for_user(session, user_id)
                    existing = await session.scalar(
                        select(LedgerEntry)
                        .where(LedgerEntry.idempotency_key == normalized_key)
                        .with_for_update()
                    )
                    if existing is not None:
                        metadata = existing.metadata_json
                        if (
                            existing.account_id != account.id
                            or existing.kind is not LedgerKind.ADJUSTMENT
                            or existing.amount != normalized_amount
                            or metadata.get("reason") != normalized_reason
                        ):
                            raise IdempotencyConflict
                        return AdjustmentResult(
                            ledger_entry_id=existing.id,
                            account_id=account.id,
                            amount=existing.amount,
                            balance=account.balance,
                            total_spent=account.total_spent,
                        )
                    if normalized_amount < 0 and account.balance < -normalized_amount:
                        raise InsufficientBalance(
                            required=-normalized_amount,
                            available=account.balance,
                        )

                    account.balance = _money(
                        account.balance + normalized_amount,
                        "adjustment balance_after",
                    )
                    account.version += 1
                    entry = LedgerEntry(
                        account_id=account.id,
                        request_id=None,
                        idempotency_key=normalized_key,
                        kind=LedgerKind.ADJUSTMENT,
                        amount=normalized_amount,
                        balance_after=account.balance,
                        metadata_json={"reason": normalized_reason},
                    )
                    session.add(entry)
                    await session.flush()
                    return AdjustmentResult(
                        ledger_entry_id=entry.id,
                        account_id=account.id,
                        amount=normalized_amount,
                        balance=account.balance,
                        total_spent=account.total_spent,
                    )
        except IntegrityError as exc:
            raise IdempotencyConflict from exc

    async def update_reservation_recovery(
        self,
        *,
        reservation_id: int,
        recovery: ReservationRecovery,
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                reservation = await session.scalar(
                    select(LedgerEntry)
                    .where(
                        LedgerEntry.id == reservation_id,
                        LedgerEntry.kind == LedgerKind.RESERVATION,
                    )
                    .with_for_update()
                )
                if reservation is None:
                    raise ReservationNotFound
                if reservation.request_id is None:
                    raise RuntimeError("reservation is missing its request ID")
                release = await session.scalar(
                    select(LedgerEntry.id).where(
                        LedgerEntry.account_id == reservation.account_id,
                        LedgerEntry.request_id == reservation.request_id,
                        LedgerEntry.kind == LedgerKind.RESERVATION_RELEASE,
                    )
                )
                if release is not None:
                    return False
                reservation.metadata_json = {
                    **reservation.metadata_json,
                    **_recovery_metadata(
                        recovery,
                        version=int(reservation.metadata_json.get("recovery_version", 0)) + 1,
                    ),
                }
                await session.flush()
                return True

    async def recover_orphaned_reservations(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
        before_settle: Callable[[int], Awaitable[None]] | None = None,
    ) -> int:
        if limit < 1:
            raise ValueError("limit must be positive")
        effective_now = (now or datetime.now(UTC)).replace(tzinfo=None)
        recovered = 0
        cursor = 0
        page_size = max(20, min(200, limit * 2))
        while recovered < limit:
            candidate_ids = await self._recovery_candidate_ids(cursor, page_size)
            if not candidate_ids:
                break
            cursor = candidate_ids[-1]
            for reservation_id in candidate_ids:
                claimed = await self._claim_expired_recovery(reservation_id, effective_now)
                if claimed is None:
                    continue
                recovery, model, claim_token = claimed
                if before_settle is not None:
                    await before_settle(reservation_id)
                try:
                    await self.settle_request(
                        reservation_id=reservation_id,
                        idempotency_key=recovery.settlement_key,
                        model=model if recovery.cost is None else None,
                        usage=recovery.usage,
                        cost=recovery.cost,
                        cost_amount=recovery.cost_amount,
                        usage_source=recovery.usage_source,
                        expected_recovery_version=recovery.version,
                        expected_recovery_claim=claim_token,
                    )
                except _RecoveryClaimLost:
                    continue
                recovered += 1
                if recovered >= limit:
                    break
        return recovered

    async def _recovery_candidate_ids(self, cursor: int, page_size: int) -> list[int]:
        release = aliased(LedgerEntry)
        release_exists = exists(
            select(release.id).where(
                release.account_id == LedgerEntry.account_id,
                release.request_id == LedgerEntry.request_id,
                release.kind == LedgerKind.RESERVATION_RELEASE,
            )
        )
        async with self._session_factory() as session:
            return list(
                await session.scalars(
                    select(LedgerEntry.id)
                    .where(
                        LedgerEntry.kind == LedgerKind.RESERVATION,
                        LedgerEntry.id > cursor,
                        ~release_exists,
                    )
                    .order_by(LedgerEntry.id)
                    .limit(page_size)
                )
            )

    async def _claim_expired_recovery(
        self,
        reservation_id: int,
        now: datetime,
    ) -> tuple[ReservationRecovery, _RecoveredModel, str] | None:
        async with self._session_factory() as session:
            async with session.begin():
                reservation = await session.scalar(
                    select(LedgerEntry)
                    .where(
                        LedgerEntry.id == reservation_id,
                        LedgerEntry.kind == LedgerKind.RESERVATION,
                    )
                    .with_for_update()
                )
                if reservation is None or reservation.request_id is None:
                    return None
                release = await session.scalar(
                    select(LedgerEntry.id).where(
                        LedgerEntry.account_id == reservation.account_id,
                        LedgerEntry.request_id == reservation.request_id,
                        LedgerEntry.kind == LedgerKind.RESERVATION_RELEASE,
                    )
                )
                recovery = _reservation_recovery(reservation.metadata_json)
                if release is not None or recovery is None or recovery.expires_at > now:
                    return None
                claim_token = uuid4().hex
                reservation.metadata_json = {
                    **reservation.metadata_json,
                    "recovery_claimed_version": recovery.version,
                    "recovery_claim_token": claim_token,
                    "recovery_claimed_at": now.isoformat(timespec="microseconds"),
                }
                model = _RecoveredModel(
                    canonical_name=str(reservation.metadata_json["model"]),
                    input_price_per_million=Decimal(
                        str(reservation.metadata_json["input_price_per_million"])
                    ),
                    output_price_per_million=Decimal(
                        str(reservation.metadata_json["output_price_per_million"])
                    ),
                    cache_read_price_per_million=_cache_price_or_zero(
                        reservation.metadata_json.get("cache_read_price_per_million")
                    ),
                    cache_write_price_per_million=_cache_price_or_zero(
                        reservation.metadata_json.get("cache_write_price_per_million")
                    ),
                )
                await session.flush()
                return recovery, model, claim_token

    async def reconcile_charge(
        self,
        *,
        user_id: int,
        request_id: str,
        amount: Decimal,
        idempotency_key: str,
        reason: str = "provider_usage_reconciliation",
    ) -> AdjustmentResult:
        normalized_amount = _money(amount, "reconciliation amount")
        if normalized_amount <= 0 or amount != normalized_amount:
            raise ValueError("reconciliation amount must be positive with at most eight decimals")
        normalized_key = _normalize_idempotency_key(idempotency_key)
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    account = await _locked_account_for_user(session, user_id)
                    existing = await session.scalar(
                        select(LedgerEntry)
                        .where(LedgerEntry.idempotency_key == normalized_key)
                        .with_for_update()
                    )
                    if existing is not None:
                        metadata = existing.metadata_json
                        if (
                            existing.account_id != account.id
                            or existing.request_id != request_id
                            or existing.kind is not LedgerKind.ADJUSTMENT
                            or existing.amount != normalized_amount
                            or metadata.get("reason") != reason
                            or metadata.get("internal_reconciliation") is not True
                        ):
                            raise IdempotencyConflict
                        return AdjustmentResult(
                            existing.id,
                            account.id,
                            existing.amount,
                            account.balance,
                            account.total_spent,
                        )
                    if account.total_spent < normalized_amount:
                        raise ValueError("reconciliation exceeds total spent")
                    account.balance = _money(
                        account.balance + normalized_amount,
                        "reconciliation balance_after",
                    )
                    account.total_spent = _money(
                        account.total_spent - normalized_amount,
                        "reconciliation total_spent",
                    )
                    if account.total_spent < 0:
                        raise BillingAmountOutOfRange("reconciliation total_spent")
                    account.version += 1
                    entry = LedgerEntry(
                        account_id=account.id,
                        request_id=request_id,
                        idempotency_key=normalized_key,
                        kind=LedgerKind.ADJUSTMENT,
                        amount=normalized_amount,
                        balance_after=account.balance,
                        metadata_json={
                            "reason": reason,
                            "internal_reconciliation": True,
                            "total_spent_after": str(account.total_spent),
                        },
                    )
                    session.add(entry)
                    await session.flush()
                    return AdjustmentResult(
                        entry.id,
                        account.id,
                        normalized_amount,
                        account.balance,
                        account.total_spent,
                    )
        except IntegrityError as exc:
            raise IdempotencyConflict from exc


def get_billing_service(request: Request) -> BillingService:
    service = getattr(request.app.state, "billing_service", None)
    if not isinstance(service, BillingService):
        raise RuntimeError("application billing service is not configured")
    return service


async def reserve_balance(
    session: AsyncSession,
    *,
    user_id: int,
    model: PricedModel,
    estimated_input_tokens: int,
    max_output_tokens: int | None,
    idempotency_key: str,
    request_id: UUID | str | None = None,
    default_max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    recovery: ReservationRecovery | None = None,
    provider: Provider | None = None,
    provider_public_multiplier: Decimal | None = None,
) -> BalanceReservation:
    return await BillingService(
        mutation_session_factory_for(session),
        default_max_output_tokens=default_max_output_tokens,
    ).reserve_balance(
        user_id=user_id,
        model=model,
        estimated_input_tokens=estimated_input_tokens,
        max_output_tokens=max_output_tokens,
        idempotency_key=idempotency_key,
        request_id=request_id,
        recovery=recovery,
        provider=provider,
        provider_public_multiplier=provider_public_multiplier,
    )


async def settle_request(
    session: AsyncSession,
    *,
    reservation_id: int,
    idempotency_key: str,
    model: PricedModel | None = None,
    usage: CanonicalUsage | None = None,
    cost: Decimal | None = None,
    cost_amount: Decimal | None = None,
    usage_source: UsageSource | None = None,
    provider: Provider | None = None,
) -> SettlementResult:
    return await BillingService(mutation_session_factory_for(session)).settle_request(
        reservation_id=reservation_id,
        idempotency_key=idempotency_key,
        model=model,
        usage=usage,
        cost=cost,
        cost_amount=cost_amount,
        usage_source=usage_source,
        provider=provider,
    )


async def adjust_balance(
    session: AsyncSession,
    *,
    user_id: int,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
) -> AdjustmentResult:
    return await BillingService(mutation_session_factory_for(session)).adjust_balance(
        user_id=user_id,
        amount=amount,
        reason=reason,
        idempotency_key=idempotency_key,
    )


async def _validate_reservation_replay(
    session: AsyncSession,
    *,
    entry: LedgerEntry,
    account_id: int,
    fingerprint: str,
) -> None:
    if (
        entry.account_id != account_id
        or entry.kind is not LedgerKind.RESERVATION
        or entry.metadata_json.get("reservation_fingerprint") != fingerprint
    ):
        raise IdempotencyConflict
    completed = await session.scalar(
        select(LedgerEntry.id)
        .where(
            LedgerEntry.account_id == account_id,
            LedgerEntry.request_id == entry.request_id,
            LedgerEntry.kind == LedgerKind.RESERVATION_RELEASE,
        )
        .with_for_update()
    )
    if completed is not None:
        raise IdempotencyConflict


async def _settlement_entries(
    session: AsyncSession,
    *,
    account_id: int,
    request_id: str,
) -> tuple[LedgerEntry | None, LedgerEntry | None]:
    entries = (
        await session.scalars(
            select(LedgerEntry)
            .where(
                LedgerEntry.account_id == account_id,
                LedgerEntry.request_id == request_id,
                LedgerEntry.kind.in_((LedgerKind.RESERVATION_RELEASE, LedgerKind.USAGE)),
            )
            .with_for_update()
        )
    ).all()
    release = next(
        (entry for entry in entries if entry.kind is LedgerKind.RESERVATION_RELEASE),
        None,
    )
    usage = next((entry for entry in entries if entry.kind is LedgerKind.USAGE), None)
    if len(entries) != int(release is not None) + int(usage is not None):
        raise IdempotencyConflict
    return release, usage


def _validate_settlement_replay(
    *,
    reservation: LedgerEntry,
    release: LedgerEntry,
    usage_entry: LedgerEntry,
    settlement_key: str,
    fingerprint: str,
) -> None:
    if reservation.request_id is None:
        raise RuntimeError("reservation is missing its request ID")
    expected_release_key = f"{settlement_key}:release"
    expected_usage_key = f"{settlement_key}:usage"
    for entry, expected_key in (
        (release, expected_release_key),
        (usage_entry, expected_usage_key),
    ):
        metadata = entry.metadata_json
        if (
            entry.account_id != reservation.account_id
            or entry.request_id != reservation.request_id
            or entry.idempotency_key != expected_key
            or metadata.get("reservation_entry_id") != reservation.id
            or metadata.get("request_id") != reservation.request_id
            or metadata.get("settlement_key") != settlement_key
            or metadata.get("settlement_fingerprint") != fingerprint
        ):
            raise IdempotencyConflict


async def _locked_account_for_user(session: AsyncSession, user_id: int) -> Account:
    account = await session.scalar(
        select(Account)
        .where(Account.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if account is None:
        raise AccountNotFound
    return account


async def _locked_account(session: AsyncSession, account_id: int) -> Account:
    account = await session.scalar(
        select(Account)
        .where(Account.id == account_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if account is None:
        raise AccountNotFound
    return account


def _settlement_cost(
    *,
    model: PricedModel | None,
    usage: CanonicalUsage | None,
    cost: Decimal | None,
    provider: Provider | None = None,
) -> Decimal:
    return _settlement_costs(
        model=model,
        usage=usage,
        cost=cost,
        cost_amount=None,
        provider=provider,
    )[0]


def _settlement_costs(
    *,
    model: PricedModel | None,
    usage: CanonicalUsage | None,
    cost: Decimal | None,
    cost_amount: Decimal | None,
    provider: Provider | None = None,
) -> tuple[Decimal, Decimal]:
    if cost is not None:
        if model is not None:
            raise TypeError("model cannot be provided with cost")
        if cost < 0:
            raise ValueError("cost must be nonnegative")
        if cost_amount is not None and cost_amount < 0:
            raise ValueError("cost_amount must be nonnegative")
        public_cost = _money(cost)
        platform_cost = public_cost if cost_amount is None else _money(cost_amount)
        return public_cost, platform_cost
    if cost_amount is not None:
        raise TypeError("cost_amount cannot be provided when cost is omitted")
    if model is None or usage is None:
        raise TypeError("model and usage are required when cost is omitted")
    model_mult, public_mult, cost_mult = get_effective_multipliers(model, provider)
    public_cost = _money(
        calculate_cost(
            model,
            usage,
            model_multiplier=model_mult,
            provider_multiplier=public_mult,
        ),
        "settlement cost",
    )
    platform_cost = _money(
        calculate_cost(
            model,
            usage,
            model_multiplier=model_mult,
            provider_multiplier=cost_mult,
        ),
        "settlement cost amount",
    )
    return public_cost, platform_cost


def _reservation_from_entry(entry: LedgerEntry, *, user_id: int) -> BalanceReservation:
    if entry.request_id is None:
        raise RuntimeError("reservation is missing its request ID")
    return BalanceReservation(
        ledger_entry_id=entry.id,
        account_id=entry.account_id,
        user_id=user_id,
        request_id=entry.request_id,
        idempotency_key=entry.idempotency_key,
        amount=_money(-entry.amount),
        balance_after=entry.balance_after,
    )


def _settlement_from_entries(
    *,
    reservation: LedgerEntry,
    usage_entry: LedgerEntry,
) -> SettlementResult:
    if reservation.request_id is None:
        raise RuntimeError("reservation is missing its request ID")
    metadata = usage_entry.metadata_json
    return SettlementResult(
        account_id=reservation.account_id,
        request_id=reservation.request_id,
        reserved_amount=_money(-reservation.amount),
        actual_cost=Decimal(str(metadata["actual_cost"])),
        charged_amount=Decimal(str(metadata["charged_amount"])),
        balance=usage_entry.balance_after,
        total_spent=Decimal(str(metadata["total_spent_after"])),
        exhausted=bool(metadata["exhausted"]),
        uncollected_amount=Decimal(str(metadata.get("uncollected_amount", "0"))),
        cost_amount=Decimal(str(metadata.get("cost_amount", metadata["actual_cost"]))),
    )


def _recovery_metadata(
    recovery: ReservationRecovery,
    *,
    version: int | None = None,
) -> dict[str, Any]:
    expires_at = recovery.expires_at
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
    effective_version = recovery.version if version is None else version
    metadata: dict[str, Any] = {
        "recovery_pending": True,
        "recovery_version": effective_version,
        "recovery_claimed_version": None,
        "recovery_claim_token": None,
        "recovery_claimed_at": None,
        "recovery_settlement_key": _normalize_idempotency_key(
            recovery.settlement_key,
            suffix_length=max(len(":release"), len(":usage")),
        ),
        "recovery_input_tokens": recovery.usage.input_tokens,
        "recovery_output_tokens": recovery.usage.output_tokens,
        "recovery_cache_read_tokens": recovery.usage.cache_read_tokens,
        "recovery_cache_write_tokens": recovery.usage.cache_write_tokens,
        "recovery_usage_source": recovery.usage_source.value,
        "recovery_expires_at": expires_at.isoformat(timespec="microseconds"),
    }
    if recovery.cost is not None:
        if recovery.cost < 0:
            raise ValueError("recovery cost must be nonnegative")
        metadata["recovery_cost"] = str(_money(recovery.cost))
    else:
        metadata["recovery_cost"] = None
    if recovery.cost_amount is not None:
        if recovery.cost_amount < 0:
            raise ValueError("recovery cost_amount must be nonnegative")
        metadata["recovery_cost_amount"] = str(_money(recovery.cost_amount))
    else:
        metadata["recovery_cost_amount"] = None
    return metadata


def _reservation_recovery(metadata: dict[str, Any]) -> ReservationRecovery | None:
    if metadata.get("recovery_pending") is not True:
        return None
    try:
        settlement_key = str(metadata["recovery_settlement_key"])
        input_tokens = int(metadata["recovery_input_tokens"])
        output_tokens = int(metadata["recovery_output_tokens"])
        cache_read_tokens = int(metadata.get("recovery_cache_read_tokens", 0))
        cache_write_tokens = int(metadata.get("recovery_cache_write_tokens", 0))
        usage_source = UsageSource(str(metadata["recovery_usage_source"]))
        expires_at = datetime.fromisoformat(str(metadata["recovery_expires_at"]))
        version = int(metadata.get("recovery_version", 0))
        raw_cost = metadata.get("recovery_cost")
        cost = Decimal(str(raw_cost)) if raw_cost is not None else None
        raw_cost_amount = metadata.get("recovery_cost_amount")
        cost_amount = Decimal(str(raw_cost_amount)) if raw_cost_amount is not None else None
    except (KeyError, TypeError, ValueError):
        return None
    if (
        input_tokens < 0
        or output_tokens < 0
        or cache_read_tokens < 0
        or cache_write_tokens < 0
        or version < 0
        or (cost is not None and cost < 0)
        or (cost_amount is not None and cost_amount < 0)
    ):
        return None
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
    return ReservationRecovery(
        settlement_key=settlement_key,
        usage=CanonicalUsage(
            input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
        ),
        usage_source=usage_source,
        expires_at=expires_at,
        cost=cost,
        cost_amount=cost_amount,
        version=version,
    )


def _reservation_fingerprint(
    *,
    account_id: int,
    user_id: int,
    request_id: str,
    model: PricedModel,
    estimated_input_tokens: int,
    max_output_tokens: int,
    reserved_amount: Decimal,
    model_multiplier: Decimal = Decimal("1.00"),
    public_multiplier: Decimal = Decimal("1.00"),
) -> str:
    return _fingerprint(
        {
            "account_id": account_id,
            "user_id": user_id,
            "request_id": request_id,
            "model": _model_name(model),
            "input_price_per_million": str(model.input_price_per_million),
            "output_price_per_million": str(model.output_price_per_million),
            "cache_read_price_per_million": str(_cache_read_price(model)),
            "cache_write_price_per_million": str(_cache_write_price(model)),
            "estimated_input_tokens": estimated_input_tokens,
            "max_output_tokens": max_output_tokens,
            "reserved_amount": str(reserved_amount),
            "model_multiplier": str(model_multiplier),
            "public_multiplier": str(public_multiplier),
        }
    )


def _settlement_fingerprint(
    *,
    reservation_id: int,
    actual_cost: Decimal,
    cost_amount: Decimal | None = None,
    usage: CanonicalUsage | None,
    usage_source: UsageSource | None,
) -> str:
    return _fingerprint(
        {
            "reservation_id": reservation_id,
            "actual_cost": str(actual_cost),
            "cost_amount": str(actual_cost if cost_amount is None else cost_amount),
            "input_tokens": usage.input_tokens if usage is not None else None,
            "output_tokens": usage.output_tokens if usage is not None else None,
            "cache_read_tokens": usage.cache_read_tokens if usage is not None else None,
            "cache_write_tokens": usage.cache_write_tokens if usage is not None else None,
            "usage_source": usage_source.value if usage_source is not None else None,
        }
    )


def _fingerprint(value: dict[str, Any]) -> str:
    return sha256(orjson.dumps(value, option=orjson.OPT_SORT_KEYS)).hexdigest()


def _model_name(model: PricedModel) -> str:
    return str(getattr(model, "canonical_name", type(model).__qualname__))


def _cache_price_or_zero(value: object) -> Decimal:
    if value is None or value == "None":
        return Decimal("0")
    return Decimal(str(value))


def _cache_read_price(model: PricedModel) -> Decimal:
    return _cache_price_or_zero(getattr(model, "cache_read_price_per_million", None))


def _cache_write_price(model: PricedModel) -> Decimal:
    return _cache_price_or_zero(getattr(model, "cache_write_price_per_million", None))


def _normalize_idempotency_key(value: str, *, suffix_length: int = 0) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("idempotency_key is required")
    if len(normalized) + suffix_length > 255:
        raise ValueError("idempotency_key is too long")
    return normalized


def _validate_money_magnitude(value: Decimal, field: str = "billing value") -> None:
    if not value.is_finite() or abs(value) > MAX_MONEY:
        raise BillingAmountOutOfRange(field)


def _money(value: Decimal, field: str = "billing value") -> Decimal:
    _validate_money_magnitude(value, field)
    try:
        normalized = value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise BillingAmountOutOfRange(field) from None
    _validate_money_magnitude(normalized, field)
    return normalized
