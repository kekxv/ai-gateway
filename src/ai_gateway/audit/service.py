from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractAsyncContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import orjson
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.audit.codec import DEFAULT_AUDIT_BODY_LIMIT_BYTES, gzip_json
from ai_gateway.audit.redaction import redact_headers, redact_json
from ai_gateway.core.config import get_settings
from ai_gateway.core.enums import Protocol, RequestStatus, UsageSource
from ai_gateway.db.models import RequestLog, RequestLogDetail
from ai_gateway.db.session import get_session_factory
from ai_gateway.transport.sse import SSEDecoder

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
Clock = Callable[[], datetime]
_current_audit_service: ContextVar[AuditService | None] = ContextVar(
    "current_audit_service",
    default=None,
)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class RequestContext:
    user_id: int
    inbound_protocol: Protocol
    transport: str
    stream: bool
    api_key_id: int | None = None
    model_id: int | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RequestResult:
    provider_id: int | None = None
    model_route_id: int | None = None
    outbound_protocol: Protocol | None = None
    http_status: int | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    usage_source: UsageSource | None = None
    cost: Decimal = Decimal("0")
    latency_ms: int | None = None
    first_token_ms: int | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RequestFailure:
    error_code: str
    client_disconnected: bool = False
    provider_id: int | None = None
    model_route_id: int | None = None
    outbound_protocol: Protocol | None = None
    http_status: int | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    usage_source: UsageSource | None = None
    cost: Decimal = Decimal("0")
    latency_ms: int | None = None
    first_token_ms: int | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class AuditService:
    """Write request audit state in isolated, failure-tolerant transactions."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        body_limit_bytes: int = DEFAULT_AUDIT_BODY_LIMIT_BYTES,
        clock: Clock = _utcnow,
    ) -> None:
        if body_limit_bytes < 1:
            raise ValueError("body_limit_bytes must be positive")
        self._session_factory = session_factory
        self._body_limit_bytes = body_limit_bytes
        self._clock = clock

    async def start_request(
        self,
        context: RequestContext,
        body: bytes,
        *,
        request_id: UUID | None = None,
    ) -> UUID:
        request_id = request_id or uuid4()
        try:
            detail = _detail(headers=context.headers, body=body, metadata=context.metadata)
            request_detail_gzip = gzip_json(detail, limit_bytes=self._body_limit_bytes)
            now = self._clock()
            async with self._session_factory() as session:
                session.add(
                    RequestLog(
                        id=str(request_id),
                        user_id=context.user_id,
                        api_key_id=context.api_key_id,
                        model_id=context.model_id,
                        inbound_protocol=context.inbound_protocol,
                        transport=context.transport,
                        stream=context.stream,
                        status=RequestStatus.STARTED,
                    )
                )
                session.add(
                    RequestLogDetail(
                        id=str(request_id),
                        request_detail_gzip=request_detail_gzip,
                        created_at=now,
                    )
                )
                await session.commit()
        except Exception as exc:
            _log_write_failure("start", request_id, exc)
        return request_id

    async def complete_request(self, request_id: UUID, result: RequestResult) -> None:
        await self._finish_request(
            request_id,
            status=RequestStatus.COMPLETED,
            provider_id=result.provider_id,
            model_route_id=result.model_route_id,
            outbound_protocol=result.outbound_protocol,
            http_status=result.http_status,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            cache_read_tokens=result.cache_read_tokens,
            cache_write_tokens=result.cache_write_tokens,
            usage_source=result.usage_source,
            cost=result.cost,
            latency_ms=result.latency_ms,
            first_token_ms=result.first_token_ms,
            error_code=None,
            headers=result.headers,
            body=result.body,
            metadata=result.metadata,
        )

    async def fail_request(self, request_id: UUID, failure: RequestFailure) -> None:
        status = (
            RequestStatus.CLIENT_DISCONNECTED
            if failure.client_disconnected
            else RequestStatus.FAILED
        )
        await self._finish_request(
            request_id,
            status=status,
            provider_id=failure.provider_id,
            model_route_id=failure.model_route_id,
            outbound_protocol=failure.outbound_protocol,
            http_status=failure.http_status,
            prompt_tokens=failure.prompt_tokens,
            completion_tokens=failure.completion_tokens,
            cache_read_tokens=failure.cache_read_tokens,
            cache_write_tokens=failure.cache_write_tokens,
            usage_source=failure.usage_source,
            cost=failure.cost,
            latency_ms=failure.latency_ms,
            first_token_ms=failure.first_token_ms,
            error_code=failure.error_code,
            headers=failure.headers,
            body=failure.body,
            metadata=failure.metadata,
        )

    async def _finish_request(
        self,
        request_id: UUID,
        *,
        status: RequestStatus,
        provider_id: int | None,
        model_route_id: int | None,
        outbound_protocol: Protocol | None,
        http_status: int | None,
        prompt_tokens: int,
        completion_tokens: int,
        cache_read_tokens: int,
        cache_write_tokens: int,
        usage_source: UsageSource | None,
        cost: Decimal,
        latency_ms: int | None,
        first_token_ms: int | None,
        error_code: str | None,
        headers: Mapping[str, str],
        body: Any | None,
        metadata: Mapping[str, Any],
    ) -> None:
        try:
            response_metadata = dict(metadata)
            response_metadata["usage"] = {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_write_tokens": cache_write_tokens,
                "source": usage_source.value if usage_source is not None else None,
            }
            response_detail_gzip = None
            if headers or body is not None or response_metadata:
                response_detail_gzip = gzip_json(
                    _detail(headers=headers, body=body, metadata=response_metadata),
                    limit_bytes=self._body_limit_bytes,
                )
            async with self._session_factory() as session:
                await session.execute(
                    update(RequestLog)
                    .where(RequestLog.id == str(request_id))
                    .values(
                        provider_id=provider_id,
                        model_route_id=model_route_id,
                        outbound_protocol=outbound_protocol,
                        status=status,
                        http_status=http_status,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cache_read_tokens=cache_read_tokens,
                        cache_write_tokens=cache_write_tokens,
                        usage_source=usage_source,
                        cost=cost,
                        latency_ms=latency_ms,
                        first_token_ms=first_token_ms,
                        error_code=error_code,
                        completed_at=self._clock(),
                    )
                )
                if response_detail_gzip is not None:
                    await session.execute(
                        update(RequestLogDetail)
                        .where(RequestLogDetail.id == str(request_id))
                        .values(response_detail_gzip=response_detail_gzip)
                    )
                await session.commit()
        except Exception as exc:
            _log_write_failure("finish", request_id, exc, status=status)


def _detail(
    *,
    headers: Mapping[str, str],
    body: Any | None,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    detail = dict(redact_json(_normalize_json(metadata)))
    if headers:
        detail["headers"] = redact_headers(headers)
    if body is not None:
        detail["body"] = _redacted_body(body, content_type=_content_type(headers))
    return detail


def _redacted_body(body: Any, *, content_type: str | None = None) -> Any:
    if isinstance(body, bytes):
        decoded = _decode_sse_bytes(body) if _is_sse(content_type) else _decode_json_bytes(body)
    elif isinstance(body, str):
        raw = body.encode("utf-8")
        if _is_sse(content_type):
            decoded = _decode_sse_bytes(raw)
        else:
            try:
                decoded = orjson.loads(body)
            except orjson.JSONDecodeError:
                decoded = _unparseable_metadata(raw)
    else:
        decoded = body
    return redact_json(_normalize_json(decoded))


def _content_type(headers: Mapping[str, str]) -> str | None:
    return next(
        (str(value) for key, value in headers.items() if str(key).lower() == "content-type"),
        None,
    )


def _is_sse(content_type: str | None) -> bool:
    return content_type is not None and content_type.split(";", 1)[0].strip().lower() == (
        "text/event-stream"
    )


def _decode_sse_bytes(body: bytes) -> dict[str, Any]:
    decoder = SSEDecoder()
    events = [*decoder.feed(body), *decoder.finish()]
    decoded_events: list[dict[str, Any]] = []
    for event in events:
        decoded_event: dict[str, Any] = {}
        if event.event is not None:
            decoded_event["event"] = event.event
        if event.event_id is not None:
            decoded_event["id"] = event.event_id
        if event.comment is not None:
            decoded_event["comment"] = event.comment.decode("utf-8", errors="replace")
        if event.data:
            if event.data == b"[DONE]":
                decoded_event["data"] = "[DONE]"
            else:
                try:
                    decoded_event["data"] = orjson.loads(event.data)
                except (UnicodeDecodeError, orjson.JSONDecodeError):
                    decoded_event["data"] = _unparseable_metadata(event.data)
        decoded_events.append(decoded_event)
    return {
        "format": "sse",
        "events": decoded_events,
        "event_count": len(decoded_events),
        "byte_length": len(body),
    }


def _decode_json_bytes(body: bytes) -> Any:
    try:
        return orjson.loads(body)
    except (UnicodeDecodeError, orjson.JSONDecodeError):
        return _unparseable_metadata(body)


def _unparseable_metadata(body: bytes) -> dict[str, Any]:
    return {
        "unparseable": True,
        "byte_length": len(body),
        "sha256": sha256(body).hexdigest(),
    }


def _normalize_json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize_json(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _normalize_json(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, bytes):
        return _normalize_json(_decode_json_bytes(value))
    if isinstance(value, Enum):
        return _normalize_json(value.value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return {"unserializable": True, "type": type(value).__name__}


def _log_write_failure(
    operation: str,
    request_id: UUID,
    exception: Exception,
    *,
    status: RequestStatus | None = None,
) -> None:
    logger.error(
        "Audit write failed operation=%s request_id=%s status=%s exception_type=%s",
        operation,
        request_id,
        status.value if status is not None else "none",
        type(exception).__name__,
    )


def _default_service() -> AuditService:
    return AuditService(
        get_session_factory(),
        body_limit_bytes=get_settings().audit_body_limit_bytes,
    )


def current_audit_service() -> AuditService:
    return _current_audit_service.get() or _default_service()


@contextmanager
def use_audit_service(service: AuditService) -> Iterator[None]:
    """Bind one app-owned audit service to the current async request context."""

    token = _current_audit_service.set(service)
    try:
        yield
    finally:
        _current_audit_service.reset(token)


async def start_request(
    context: RequestContext,
    body: bytes,
    *,
    request_id: UUID | None = None,
) -> UUID:
    try:
        service = current_audit_service()
    except Exception as exc:
        fallback_id = request_id or uuid4()
        _log_write_failure("start", fallback_id, exc)
        return fallback_id
    return await service.start_request(context, body, request_id=request_id)


async def complete_request(request_id: UUID, result: RequestResult) -> None:
    try:
        service = current_audit_service()
    except Exception as exc:
        _log_write_failure("finish", request_id, exc, status=RequestStatus.COMPLETED)
        return
    await service.complete_request(request_id, result)


async def fail_request(request_id: UUID, failure: RequestFailure) -> None:
    try:
        service = current_audit_service()
    except Exception as exc:
        failure_status = (
            RequestStatus.CLIENT_DISCONNECTED
            if failure.client_disconnected
            else RequestStatus.FAILED
        )
        _log_write_failure("finish", request_id, exc, status=failure_status)
        return
    await service.fail_request(request_id, failure)
