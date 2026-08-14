from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_gateway.core.enums import ModelType, Protocol, RouteRuntimeState, RouteSource, enum_values
from ai_gateway.db.base import Base

if TYPE_CHECKING:
    from ai_gateway.db.models.identity import ApiKeyModel, ApiKeyProvider


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    credential_encrypted: Mapped[bytes] = mapped_column(LONGBLOB)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    auto_load_models: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("0"),
    )
    model_sync_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        default=3600,
        server_default=text("3600"),
    )
    last_model_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cost_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        default=Decimal("1.00"),
        server_default=text("1.00"),
        nullable=False,
    )
    public_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        default=Decimal("1.00"),
        server_default=text("1.00"),
        nullable=False,
    )

    protocols: Mapped[list[ProviderProtocol]] = relationship(
        back_populates="provider",
        cascade="all, delete-orphan",
    )
    routes: Mapped[list[ModelRoute]] = relationship(back_populates="provider")
    api_key_links: Mapped[list[ApiKeyProvider]] = relationship(back_populates="provider")


class ProviderProtocol(Base):
    __tablename__ = "provider_protocols"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "protocol",
            "base_url",
            name="uq_provider_protocols_provider_protocol_base_url",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    protocol: Mapped[Protocol] = mapped_column(
        Enum(Protocol, name="protocol", values_callable=enum_values)
    )
    base_url: Mapped[str] = mapped_column(String(512))
    websocket_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    extra_headers_encrypted: Mapped[bytes | None] = mapped_column(LONGBLOB, nullable=True)
    supports_responses: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("1"),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))

    provider: Mapped[Provider] = relationship(back_populates="protocols")


class Model(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    model_type: Mapped[ModelType] = mapped_column(
        Enum(ModelType, name="model_type", values_callable=enum_values),
        default=ModelType.TEXT,
        server_default=ModelType.TEXT.value,
    )
    model_types: Mapped[list[ModelType]] = mapped_column(
        JSON,
        default=lambda: [ModelType.TEXT],
        server_default=text("(JSON_ARRAY('text'))"),
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    input_price_per_million: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
        server_default=text("0.00000000"),
    )
    output_price_per_million: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
        server_default=text("0.00000000"),
    )
    cache_read_price_per_million: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
        server_default=text("0.00000000"),
    )
    cache_write_price_per_million: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
        server_default=text("0.00000000"),
    )
    price_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        default=Decimal("1.00"),
        server_default=text("1.00"),
        nullable=False,
    )
    routing_strategy: Mapped[str] = mapped_column(
        Enum("weighted_random", name="routing_strategy"),
        default="weighted_random",
        server_default="weighted_random",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    aliases: Mapped[list[ModelAlias]] = relationship(
        back_populates="model",
        cascade="all, delete-orphan",
    )
    routes: Mapped[list[ModelRoute]] = relationship(
        back_populates="model",
        cascade="all, delete-orphan",
    )
    api_key_links: Mapped[list[ApiKeyModel]] = relationship(back_populates="model")
    price_tiers: Mapped[list[ModelPriceTier]] = relationship(
        back_populates="model",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    time_price_rules: Mapped[list[ModelTimePriceRule]] = relationship(
        back_populates="model",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


def _normalized_model_types(values: list[ModelType] | None) -> list[ModelType]:
    if not values or len(values) != len(set(values)):
        raise ValueError("model_types must contain unique values")
    return [ModelType(value) for value in values]


@event.listens_for(Model, "before_insert")
def synchronize_new_model_types(_mapper: object, _connection: object, target: Model) -> None:
    model_types_history = inspect(target).attrs.model_types.history
    if model_types_history.added:
        target.model_types = _normalized_model_types(target.model_types)
        target.model_type = target.model_types[0]
    else:
        target.model_types = [target.model_type or ModelType.TEXT]


@event.listens_for(Model, "before_update")
def synchronize_updated_model_types(_mapper: object, _connection: object, target: Model) -> None:
    state = inspect(target)
    model_types_history = state.attrs.model_types.history
    if model_types_history.has_changes():
        target.model_types = _normalized_model_types(target.model_types)
        target.model_type = target.model_types[0]
    elif state.attrs.model_type.history.has_changes():
        target.model_types = [target.model_type]
    else:
        target.model_types = _normalized_model_types(target.model_types)


class ModelPriceTier(Base):
    __tablename__ = "model_price_tiers"
    __table_args__ = (
        Index(
            "ix_model_price_tiers_model_max_input",
            "model_id",
            "max_input_tokens",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"))
    max_input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    input_price_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    output_price_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    cache_read_price_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    cache_write_price_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8))

    model: Mapped[Model] = relationship(back_populates="price_tiers")


class ModelTimePriceRule(Base):
    __tablename__ = "model_time_price_rules"
    __table_args__ = (Index("ix_model_time_price_rules_model", "model_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"))
    weekdays: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time] = mapped_column()
    end_time: Mapped[time] = mapped_column()
    effective_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    input_price_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    output_price_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    cache_read_price_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    cache_write_price_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8))

    model: Mapped[Model] = relationship(back_populates="time_price_rules")


class ModelAlias(Base):
    __tablename__ = "model_aliases"
    __table_args__ = (
        UniqueConstraint("model_id", "alias", name="uq_model_aliases_model_alias"),
        Index("ix_model_aliases_alias", "alias"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    alias: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))

    model: Mapped[Model] = relationship(back_populates="aliases")


class ModelRoute(Base):
    __tablename__ = "model_routes"
    __table_args__ = (
        UniqueConstraint(
            "model_id",
            "provider_id",
            name="uq_model_routes_model_provider",
        ),
        Index(
            "ix_model_routes_model_enabled_runtime_state",
            "model_id",
            "enabled",
            "runtime_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    upstream_model: Mapped[str] = mapped_column(String(255))
    weight: Mapped[int] = mapped_column(Integer, default=100, server_default=text("100"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    source: Mapped[RouteSource] = mapped_column(
        Enum(RouteSource, name="route_source", values_callable=enum_values),
        default=RouteSource.MANUAL,
        server_default=RouteSource.MANUAL.value,
    )
    runtime_state: Mapped[RouteRuntimeState] = mapped_column(
        Enum(RouteRuntimeState, name="route_runtime_state", values_callable=enum_values),
        default=RouteRuntimeState.CLOSED,
        server_default=RouteRuntimeState.CLOSED.value,
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
    )
    disabled_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    model: Mapped[Model] = relationship(back_populates="routes")
    provider: Mapped[Provider] = relationship(back_populates="routes")
