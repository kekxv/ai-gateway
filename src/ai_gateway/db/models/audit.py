from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_gateway.core.enums import Protocol, RequestStatus, UsageSource, enum_values
from ai_gateway.db.base import Base


class RequestLog(Base):
    __tablename__ = "request_logs"
    __table_args__ = (
        Index("ix_request_logs_created_at", "created_at"),
        Index("ix_request_logs_model_created_at", "model_id", "created_at"),
        Index("ix_request_logs_user_created_at", "user_id", "created_at"),
        Index("ix_request_logs_api_key_created_at", "api_key_id", "created_at"),
        Index("ix_request_logs_provider_created_at", "provider_id", "created_at"),
        Index("ix_request_logs_status_created_at", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"), nullable=True)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id"), nullable=True)
    model_route_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_routes.id"),
        nullable=True,
    )
    inbound_protocol: Mapped[Protocol] = mapped_column(
        Enum(Protocol, name="protocol", values_callable=enum_values)
    )
    outbound_protocol: Mapped[Protocol | None] = mapped_column(
        Enum(Protocol, name="protocol", values_callable=enum_values),
        nullable=True,
    )
    transport: Mapped[str] = mapped_column(String(32))
    stream: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="request_status", values_callable=enum_values),
        default=RequestStatus.STARTED,
        server_default=RequestStatus.STARTED.value,
    )
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
    )
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    usage_source: Mapped[UsageSource | None] = mapped_column(
        Enum(UsageSource, name="usage_source", values_callable=enum_values),
        nullable=True,
    )
    cost: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
        server_default=text("0.00000000"),
    )
    cost_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
        server_default=text("0.00000000"),
        nullable=False,
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_token_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 关联的详情记录（1:1 关系）
    detail: Mapped[RequestLogDetail | None] = relationship(
        "RequestLogDetail",
        back_populates="request_log",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )


class RequestLogDetail(Base):
    """审计日志详情表 - 存储请求和响应的完整详情（gzip 压缩）"""

    __tablename__ = "request_log_details"
    __table_args__ = (Index("ix_request_log_details_created_at", "created_at"),)

    # 使用与 RequestLog 相同的 ID 作为主键（1:1 关系）
    id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("request_logs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    request_detail_gzip: Mapped[bytes | None] = mapped_column(LONGBLOB, nullable=True)
    response_detail_gzip: Mapped[bytes | None] = mapped_column(LONGBLOB, nullable=True)

    # 冗余存储 created_at 便于独立查询和清理（避免 JOIN）
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )

    # 反向关联
    request_log: Mapped[RequestLog] = relationship(
        "RequestLog",
        back_populates="detail",
    )


class ConfigAuditLog(Base):
    """Configuration change audit log for tracking price_multiplier updates."""

    __tablename__ = "config_audit_logs"
    __table_args__ = (
        Index("ix_config_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_config_audit_logs_user_id", "user_id"),
        Index("ix_config_audit_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[int] = mapped_column(Integer)
    old_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
