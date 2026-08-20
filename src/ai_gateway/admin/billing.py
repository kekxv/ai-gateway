from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.dependencies import admin_user, current_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.billing.service import BillingError, BillingService, get_billing_service
from ai_gateway.core.datetime import UtcDatetime
from ai_gateway.core.enums import LedgerKind
from ai_gateway.db.models import Account, LedgerEntry, User
from ai_gateway.db.session import get_session

router = APIRouter(tags=["billing"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
CurrentUser = Annotated[User, Depends(current_user)]
Billing = Annotated[BillingService, Depends(get_billing_service)]


class BalanceAdjustmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(max_digits=20, decimal_places=8)
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=255)

    @field_validator("amount")
    @classmethod
    def amount_must_be_nonzero(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("amount must be nonzero")
        return value

    @field_validator("reason", "idempotency_key", mode="before")
    @classmethod
    def strip_required_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class BalanceResponse(BaseModel):
    balance: Decimal
    total_spent: Decimal


class BalanceAdjustmentResponse(BalanceResponse):
    ledger_entry_id: int
    amount: Decimal


class LedgerEntryResponse(BaseModel):
    id: int
    request_id: str | None
    idempotency_key: str
    kind: LedgerKind
    amount: Decimal
    balance_after: Decimal
    metadata: dict[str, Any]
    created_at: UtcDatetime


@router.get("/admin/users/{user_id}/ledger", response_model=list[LedgerEntryResponse])
async def list_user_ledger(
    user_id: int,
    session: Session,
    _: AdminUser,
) -> list[LedgerEntryResponse]:
    account = await session.scalar(select(Account).where(Account.user_id == user_id))
    if account is None:
        raise_auth_error(status.HTTP_404_NOT_FOUND, "user_not_found", "User not found")
    entries = (
        await session.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.account_id == account.id)
            .order_by(LedgerEntry.id.desc())
        )
    ).all()
    return [
        LedgerEntryResponse(
            id=entry.id,
            request_id=entry.request_id,
            idempotency_key=entry.idempotency_key,
            kind=entry.kind,
            amount=entry.amount,
            balance_after=entry.balance_after,
            metadata=entry.metadata_json,
            created_at=entry.created_at,
        )
        for entry in entries
    ]


@router.post(
    "/admin/users/{user_id}/balance-adjustments",
    response_model=BalanceAdjustmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_balance_adjustment(
    user_id: int,
    payload: BalanceAdjustmentCreate,
    billing: Billing,
    _: AdminUser,
) -> BalanceAdjustmentResponse:
    try:
        result = await billing.adjust_balance(
            user_id=user_id,
            amount=payload.amount,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
        )
    except BillingError as exc:
        raise_auth_error(exc.status_code, exc.code, exc.message)
    return BalanceAdjustmentResponse(
        ledger_entry_id=result.ledger_entry_id,
        amount=result.amount,
        balance=result.balance,
        total_spent=result.total_spent,
    )


@router.get("/me/balance", response_model=BalanceResponse)
async def get_personal_balance(
    session: Session,
    user: CurrentUser,
) -> BalanceResponse:
    account = await session.scalar(select(Account).where(Account.user_id == user.id))
    if account is None:
        raise_auth_error(
            status.HTTP_404_NOT_FOUND,
            "account_not_found",
            "Billing account not found",
        )
    return BalanceResponse(balance=account.balance, total_spent=account.total_spent)
