from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CHAR,
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_gateway.core.enums import LedgerKind, enum_values
from ai_gateway.db.base import Base

if TYPE_CHECKING:
    from ai_gateway.db.models.identity import User


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
        server_default=text("0.00000000"),
    )
    total_spent: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
        server_default=text("0.00000000"),
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))

    user: Mapped[User] = relationship(back_populates="account")
    ledger_entries: Mapped[list[LedgerEntry]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    request_id: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    kind: Mapped[LedgerKind] = mapped_column(
        Enum(LedgerKind, name="ledger_kind", values_callable=enum_values)
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="ledger_entries")
