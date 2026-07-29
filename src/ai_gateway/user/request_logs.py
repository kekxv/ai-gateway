from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import orjson
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.dependencies import current_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.core.enums import Protocol, RequestStatus, UsageSource
from ai_gateway.db.models import ApiKey, Model, ModelRoute, Provider, RequestLog, User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/user/request-logs", tags=["user-request-logs"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(current_user)]
PageSize = Annotated[int, Query(ge=1, le=200)]


class RequestLogSummary(BaseModel):
    id: UUID
    api_key_id: int | None
    api_key_prefix: str | None
    model_id: int | None
    model_name: str | None
    provider_id: int | None
    provider_name: str | None
    model_route_id: int | None
    route_upstream_model: str | None
    inbound_protocol: Protocol
    outbound_protocol: Protocol | None
    transport: str
    stream: bool
    status: RequestStatus
    http_status: int | None
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    usage_source: UsageSource | None
    cost: Any
    latency_ms: int | None
    first_token_ms: int | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None


class RequestLogListResponse(BaseModel):
    items: list[RequestLogSummary]
    next_cursor: str | None


class RequestLogDetail(RequestLogSummary):
    pass


_SUMMARY_COLUMNS = (
    RequestLog.id,
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
    RequestLog.cache_read_tokens,
    RequestLog.cache_write_tokens,
    RequestLog.usage_source,
    RequestLog.cost,
    RequestLog.latency_ms,
    RequestLog.first_token_ms,
    RequestLog.error_code,
    RequestLog.created_at,
    RequestLog.completed_at,
)

_IDENTITY_COLUMNS = (
    ApiKey.key_prefix.label("api_key_prefix"),
    Model.canonical_name.label("model_name"),
    Provider.name.label("provider_name"),
    ModelRoute.upstream_model.label("route_upstream_model"),
)


def _summary_query() -> Select[Any]:
    return (
        select(*_SUMMARY_COLUMNS, *_IDENTITY_COLUMNS)
        .select_from(RequestLog)
        .outerjoin(ApiKey, ApiKey.id == RequestLog.api_key_id)
        .outerjoin(Model, Model.id == RequestLog.model_id)
        .outerjoin(Provider, Provider.id == RequestLog.provider_id)
        .outerjoin(ModelRoute, ModelRoute.id == RequestLog.model_route_id)
    )


@router.get("", response_model=RequestLogListResponse)
async def list_user_request_logs(
    session: Session,
    user: CurrentUser,
    request_id: UUID | None = None,
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
    query = _summary_query().where(RequestLog.user_id == user.id)
    query = _apply_filters(
        query,
        request_id=request_id,
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
async def get_user_request_log(
    request_id: UUID,
    session: Session,
    user: CurrentUser,
) -> RequestLogDetail:
    row = (
        (
            await session.execute(
                _summary_query().where(
                    RequestLog.id == str(request_id),
                    RequestLog.user_id == user.id,
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise_auth_error(
            status.HTTP_404_NOT_FOUND,
            "request_log_not_found",
            "Request log not found",
        )
    return RequestLogDetail(**dict(row))


def _apply_filters(
    query: Select[Any],
    *,
    request_id: UUID | None,
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
