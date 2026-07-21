from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.billing.pricing import MONEY_QUANTUM, PricedModel, calculate_cost
from ai_gateway.core.enums import LedgerKind, UsageSource
from ai_gateway.core.errors import GatewayError
from ai_gateway.db.models import Account, LedgerEntry
from ai_gateway.protocols.types import CanonicalUsage

DEFAULT_MAX_OUTPUT_TOKENS = 4096


class BillingError(GatewayError):
    """Base error for a balance mutation that cannot be completed."""


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
        super().__init__("Idempotency key was already used for another billing operation")


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


@dataclass(frozen=True, slots=True)
class AdjustmentResult:
    ledger_entry_id: int
    account_id: int
    amount: Decimal
    balance: Decimal
    total_spent: Decimal


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
) -> BalanceReservation:
    if estimated_input_tokens < 0:
        raise ValueError("estimated_input_tokens must be nonnegative")
    selected_max_output = (
        default_max_output_tokens if max_output_tokens is None else max_output_tokens
    )
    if selected_max_output < 0:
        raise ValueError("max_output_tokens must be nonnegative")
    if default_max_output_tokens < 1:
        raise ValueError("default_max_output_tokens must be positive")
    _validate_idempotency_key(idempotency_key)
    normalized_request_id = str(request_id or uuid4())
    reserved_amount = calculate_cost(
        model,
        CanonicalUsage(estimated_input_tokens, selected_max_output),
    )

    try:
        account = await _locked_account_for_user(session, user_id)
        existing = await session.scalar(
            select(LedgerEntry)
            .where(LedgerEntry.idempotency_key == idempotency_key)
            .with_for_update()
        )
        if existing is not None:
            if existing.account_id != account.id or existing.kind is not LedgerKind.RESERVATION:
                raise IdempotencyConflict
            await session.commit()
            return _reservation_from_entry(existing, user_id=user_id)
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
            raise InsufficientBalance(required=reserved_amount, available=account.balance)

        account.balance = _money(account.balance - reserved_amount)
        account.version += 1
        entry = LedgerEntry(
            account_id=account.id,
            request_id=normalized_request_id,
            idempotency_key=idempotency_key,
            kind=LedgerKind.RESERVATION,
            amount=-reserved_amount,
            balance_after=account.balance,
            metadata_json={
                "estimated_input_tokens": estimated_input_tokens,
                "max_output_tokens": selected_max_output,
                "model": getattr(model, "canonical_name", None),
                "reserved_amount": str(reserved_amount),
            },
        )
        session.add(entry)
        await session.flush()
        result = BalanceReservation(
            ledger_entry_id=entry.id,
            account_id=account.id,
            user_id=user_id,
            request_id=normalized_request_id,
            idempotency_key=idempotency_key,
            amount=reserved_amount,
            balance_after=account.balance,
        )
        await session.commit()
        return result
    except IntegrityError as exc:
        if session.in_transaction():
            await session.rollback()
        raise IdempotencyConflict from exc
    except Exception:
        if session.in_transaction():
            await session.rollback()
        raise


async def settle_request(
    session: AsyncSession,
    *,
    reservation_id: int,
    idempotency_key: str,
    model: PricedModel | None = None,
    usage: CanonicalUsage | None = None,
    cost: Decimal | None = None,
    usage_source: UsageSource | None = None,
) -> SettlementResult:
    _validate_idempotency_key(idempotency_key, suffix_length=len(":release"))
    actual_cost = _settlement_cost(model=model, usage=usage, cost=cost)
    reservation = await session.get(LedgerEntry, reservation_id)
    if reservation is None or reservation.kind is not LedgerKind.RESERVATION:
        if session.in_transaction():
            await session.rollback()
        raise ReservationNotFound

    try:
        account = await _locked_account(session, reservation.account_id)
        reservation = await session.scalar(
            select(LedgerEntry)
            .where(LedgerEntry.id == reservation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if reservation is None or reservation.kind is not LedgerKind.RESERVATION:
            raise ReservationNotFound
        if reservation.request_id is None:
            raise RuntimeError("reservation is missing its request ID")

        existing_release = await session.scalar(
            select(LedgerEntry)
            .where(
                LedgerEntry.account_id == account.id,
                LedgerEntry.request_id == reservation.request_id,
                LedgerEntry.kind == LedgerKind.RESERVATION_RELEASE,
            )
            .with_for_update()
        )
        if existing_release is not None:
            existing_usage = await session.scalar(
                select(LedgerEntry)
                .where(
                    LedgerEntry.account_id == account.id,
                    LedgerEntry.request_id == reservation.request_id,
                    LedgerEntry.kind == LedgerKind.USAGE,
                )
                .with_for_update()
            )
            if existing_usage is None:
                raise RuntimeError("settled reservation is missing its usage ledger entry")
            await session.commit()
            return _settlement_from_entries(
                reservation=reservation,
                usage_entry=existing_usage,
            )

        reserved_amount = _money(-reservation.amount)
        balance_after_release = _money(account.balance + reserved_amount)
        charged_amount = min(actual_cost, balance_after_release)
        final_balance = _money(balance_after_release - charged_amount)
        total_spent = _money(account.total_spent + charged_amount)
        exhausted = final_balance == 0
        uncollected = _money(actual_cost - charged_amount)

        release = LedgerEntry(
            account_id=account.id,
            request_id=reservation.request_id,
            idempotency_key=f"{idempotency_key}:release",
            kind=LedgerKind.RESERVATION_RELEASE,
            amount=reserved_amount,
            balance_after=balance_after_release,
            metadata_json={"reservation_entry_id": reservation.id},
        )
        usage_metadata: dict[str, Any] = {
            "reservation_entry_id": reservation.id,
            "actual_cost": str(actual_cost),
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
            idempotency_key=f"{idempotency_key}:usage",
            kind=LedgerKind.USAGE,
            amount=-charged_amount,
            balance_after=final_balance,
            metadata_json=usage_metadata,
        )
        account.balance = final_balance
        account.total_spent = total_spent
        account.version += 1
        session.add_all((release, usage_entry))
        await session.flush()
        result = SettlementResult(
            account_id=account.id,
            request_id=reservation.request_id,
            reserved_amount=reserved_amount,
            actual_cost=actual_cost,
            charged_amount=charged_amount,
            balance=final_balance,
            total_spent=total_spent,
            exhausted=exhausted,
        )
        await session.commit()
        return result
    except IntegrityError as exc:
        if session.in_transaction():
            await session.rollback()
        raise IdempotencyConflict from exc
    except Exception:
        if session.in_transaction():
            await session.rollback()
        raise


async def adjust_balance(
    session: AsyncSession,
    *,
    user_id: int,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
) -> AdjustmentResult:
    normalized_amount = _money(amount)
    if amount != normalized_amount:
        raise ValueError("adjustment amount has more than eight decimal places")
    if normalized_amount == 0:
        raise ValueError("adjustment amount must be nonzero")
    if not reason.strip():
        raise ValueError("adjustment reason is required")
    _validate_idempotency_key(idempotency_key)

    try:
        account = await _locked_account_for_user(session, user_id)
        existing = await session.scalar(
            select(LedgerEntry)
            .where(LedgerEntry.idempotency_key == idempotency_key)
            .with_for_update()
        )
        if existing is not None:
            metadata = existing.metadata_json
            if (
                existing.account_id != account.id
                or existing.kind is not LedgerKind.ADJUSTMENT
                or existing.amount != normalized_amount
                or metadata.get("reason") != reason
            ):
                raise IdempotencyConflict
            await session.commit()
            return AdjustmentResult(
                ledger_entry_id=existing.id,
                account_id=account.id,
                amount=existing.amount,
                balance=existing.balance_after,
                total_spent=account.total_spent,
            )
        if normalized_amount < 0 and account.balance < -normalized_amount:
            raise InsufficientBalance(required=-normalized_amount, available=account.balance)

        account.balance = _money(account.balance + normalized_amount)
        account.version += 1
        entry = LedgerEntry(
            account_id=account.id,
            request_id=None,
            idempotency_key=idempotency_key,
            kind=LedgerKind.ADJUSTMENT,
            amount=normalized_amount,
            balance_after=account.balance,
            metadata_json={"reason": reason},
        )
        session.add(entry)
        await session.flush()
        result = AdjustmentResult(
            ledger_entry_id=entry.id,
            account_id=account.id,
            amount=normalized_amount,
            balance=account.balance,
            total_spent=account.total_spent,
        )
        await session.commit()
        return result
    except IntegrityError as exc:
        if session.in_transaction():
            await session.rollback()
        raise IdempotencyConflict from exc
    except Exception:
        if session.in_transaction():
            await session.rollback()
        raise


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
) -> Decimal:
    if cost is not None:
        if model is not None or usage is not None:
            raise TypeError("provide either cost or model and usage")
        if cost < 0:
            raise ValueError("cost must be nonnegative")
        return _money(cost)
    if model is None or usage is None:
        raise TypeError("model and usage are required when cost is omitted")
    return calculate_cost(model, usage)


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
    )


def _validate_idempotency_key(value: str, *, suffix_length: int = 0) -> None:
    if not value or not value.strip():
        raise ValueError("idempotency_key is required")
    if len(value) + suffix_length > 255:
        raise ValueError("idempotency_key is too long")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
