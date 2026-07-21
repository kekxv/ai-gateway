from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, LargeBinary, String, func, text
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.mysql import BINARY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_gateway.core.enums import ApiKeyScope, enum_values
from ai_gateway.db.base import Base

if TYPE_CHECKING:
    from ai_gateway.db.models.billing import Account
    from ai_gateway.db.models.catalog import Model, Provider


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(
        Enum("admin", "user", name="user_role"),
        default="user",
        server_default="user",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    totp_secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary(512), nullable=True)
    pending_totp_secret_encrypted: Mapped[bytes | None] = mapped_column(
        mysql.LONGBLOB,
        nullable=True,
    )
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    account: Mapped[Account | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    key_prefix: Mapped[str] = mapped_column(String(12))
    key_hash: Mapped[bytes] = mapped_column(BINARY(32), unique=True)
    scope: Mapped[ApiKeyScope] = mapped_column(
        Enum(ApiKeyScope, name="api_key_scope", values_callable=enum_values),
        default=ApiKeyScope.ALL,
        server_default=ApiKeyScope.ALL.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="api_keys")
    provider_links: Mapped[list[ApiKeyProvider]] = relationship(
        back_populates="api_key",
        cascade="all, delete-orphan",
    )
    model_links: Mapped[list[ApiKeyModel]] = relationship(
        back_populates="api_key",
        cascade="all, delete-orphan",
    )


class ApiKeyProvider(Base):
    __tablename__ = "api_key_providers"

    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"), primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), primary_key=True)

    api_key: Mapped[ApiKey] = relationship(back_populates="provider_links")
    provider: Mapped[Provider] = relationship(back_populates="api_key_links")


class ApiKeyModel(Base):
    __tablename__ = "api_key_models"

    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"), primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), primary_key=True)

    api_key: Mapped[ApiKey] = relationship(back_populates="model_links")
    model: Mapped[Model] = relationship(back_populates="api_key_links")
