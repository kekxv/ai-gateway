from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

import orjson
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.audit.codec import gunzip_json
from ai_gateway.auth.dependencies import admin_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.core.enums import Protocol, RequestStatus, UsageSource
from ai_gateway.db.models import RequestLog, User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/admin/request-logs", tags=["admin-request-logs"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
PageSize = Annotated[int, Query(ge=1, le=200)]


class RequestLogSummary(BaseModel):
    id: UUID
    user_id: int
    api_key_id: int | None
    model_id: int | None
    provider_id: int | None
    model_route_id: int | None
    inbound_protocol: Protocol
    outbound_protocol: Protocol | None
    transport: str
    stream: bool
    status: RequestStatus
    http_status: int | None
    prompt_tokens: int
    completion_tokens: int
    usage_source: UsageSource | None
    cost: Decimal
    latency_ms: int | None
    first_token_ms: int | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None


class RequestLogListResponse(BaseModel):
    items: list[RequestLogSummary]
    next_cursor: str | None


class RequestLogDetail(RequestLogSummary):
    request_detail: dict[str, Any] | None
    response_detail: dict[str, Any] | None


_SUMMARY_COLUMNS = (
    RequestLog.id,
    RequestLog.user_id,
    RequestLog.api_key_id,
    RequestLog.model_id,
    RequestLog.provider_id,
    RequestLog.model_route_id,
    RequestLog.inbound_protocol,
    RequestLog.outbound_protocol,
    RequestLog.transport,
    RequestLog.stream,
    RequestLog.status,
    RequestLog.http_status,
    RequestLog.prompt_tokens,
    RequestLog.completion_tokens,
    RequestLog.usage_source,
    RequestLog.cost,
    RequestLog.latency_ms,
    RequestLog.first_token_ms,
    RequestLog.error_code,
    RequestLog.created_at,
    RequestLog.completed_at,
)


@router.get("", response_model=RequestLogListResponse)
async def list_request_logs(
    session: Session,
    _: AdminUser,
    request_id: UUID | None = None,
    user_id: int | None = None,
    api_key_id: int | None = None,
    model_id: int | None = None,
    provider_id: int | None = None,
    status_filter: Annotated[RequestStatus | None, Query(alias="status")] = None,
    protocol_filter: Annotated[Protocol | None, Query(alias="protocol")] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    cursor: str | None = None,
    page_size: PageSize = 50,
) -> RequestLogListResponse:
    query = select(*_SUMMARY_COLUMNS)
    query = _apply_filters(
        query,
        request_id=request_id,
        user_id=user_id,
        api_key_id=api_key_id,
        model_id=model_id,
        provider_id=provider_id,
        status_filter=status_filter,
        protocol_filter=protocol_filter,
        created_from=created_from,
        created_to=created_to,
    )
    if cursor is not None:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                RequestLog.created_at < cursor_created_at,
                and_(
                    RequestLog.created_at == cursor_created_at,
                    RequestLog.id < cursor_id,
                ),
            )
        )
    rows = (
        (
            await session.execute(
                query.order_by(RequestLog.created_at.desc(), RequestLog.id.desc()).limit(
                    page_size + 1
                )
            )
        )
        .mappings()
        .all()
    )
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    items = [RequestLogSummary.model_validate(dict(row)) for row in page_rows]
    next_cursor = None
    if has_more and page_rows:
        next_cursor = _encode_cursor(page_rows[-1]["created_at"], page_rows[-1]["id"])
    return RequestLogListResponse(items=items, next_cursor=next_cursor)


@router.get("/{request_id}", response_model=RequestLogDetail)
async def get_request_log(
    request_id: UUID,
    session: Session,
    _: AdminUser,
) -> RequestLogDetail:
    request_log = await session.get(RequestLog, str(request_id))
    if request_log is None:
        raise_auth_error(
            status.HTTP_404_NOT_FOUND,
            "request_log_not_found",
            "Request log not found",
        )
    return RequestLogDetail(
        **_summary_values(request_log),
        request_detail=(
            gunzip_json(request_log.request_detail_gzip)
            if request_log.request_detail_gzip is not None
            else None
        ),
        response_detail=(
            gunzip_json(request_log.response_detail_gzip)
            if request_log.response_detail_gzip is not None
            else None
        ),
    )


def _apply_filters(
    query: Select[Any],
    *,
    request_id: UUID | None,
    user_id: int | None,
    api_key_id: int | None,
    model_id: int | None,
    provider_id: int | None,
    status_filter: RequestStatus | None,
    protocol_filter: Protocol | None,
    created_from: datetime | None,
    created_to: datetime | None,
) -> Select[Any]:
    if request_id is not None:
        query = query.where(RequestLog.id == str(request_id))
    if user_id is not None:
        query = query.where(RequestLog.user_id == user_id)
    if api_key_id is not None:
        query = query.where(RequestLog.api_key_id == api_key_id)
    if model_id is not None:
        query = query.where(RequestLog.model_id == model_id)
    if provider_id is not None:
        query = query.where(RequestLog.provider_id == provider_id)
    if status_filter is not None:
        query = query.where(RequestLog.status == status_filter)
    if protocol_filter is not None:
        query = query.where(
            or_(
                RequestLog.inbound_protocol == protocol_filter,
                RequestLog.outbound_protocol == protocol_filter,
            )
        )
    if created_from is not None:
        query = query.where(RequestLog.created_at >= _database_datetime(created_from))
    if created_to is not None:
        query = query.where(RequestLog.created_at <= _database_datetime(created_to))
    return query


def _summary_values(request_log: RequestLog) -> dict[str, Any]:
    return {column.key: getattr(request_log, column.key) for column in _SUMMARY_COLUMNS}


def _database_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _encode_cursor(created_at: datetime, request_id: str) -> str:
    payload = orjson.dumps([created_at.isoformat(timespec="microseconds"), request_id])
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = orjson.loads(base64.urlsafe_b64decode(cursor + padding))
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError
        created_at = datetime.fromisoformat(str(payload[0]))
        request_id = str(UUID(str(payload[1])))
    except (ValueError, TypeError, binascii.Error, orjson.JSONDecodeError):
        raise_auth_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_cursor",
            "Request log cursor is invalid",
        )
    return _database_datetime(created_at), request_id
