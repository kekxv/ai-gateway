from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import orjson
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.audit.codec import DEFAULT_AUDIT_BODY_LIMIT_BYTES, gzip_json
from ai_gateway.audit.redaction import redact_headers, redact_json
from ai_gateway.core.config import get_settings
from ai_gateway.core.enums import Protocol, RequestStatus, UsageSource
from ai_gateway.db.models import RequestLog
from ai_gateway.db.session import get_session_factory

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
Clock = Callable[[], datetime]


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

    async def start_request(self, context: RequestContext, body: bytes) -> UUID:
        request_id = uuid4()
        try:
            detail = _detail(headers=context.headers, body=body, metadata=context.metadata)
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
                        request_detail_gzip=gzip_json(
                            detail,
                            limit_bytes=self._body_limit_bytes,
                        ),
                    )
                )
                await session.commit()
        except Exception:
            logger.exception(
                "Audit write failed operation=start request_id=%s",
                request_id,
            )
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
            response_detail_gzip = None
            if headers or body is not None or metadata:
                response_detail_gzip = gzip_json(
                    _detail(headers=headers, body=body, metadata=metadata),
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
                        usage_source=usage_source,
                        cost=cost,
                        latency_ms=latency_ms,
                        first_token_ms=first_token_ms,
                        error_code=error_code,
                        response_detail_gzip=response_detail_gzip,
                        completed_at=self._clock(),
                    )
                )
                await session.commit()
        except Exception:
            logger.exception(
                "Audit write failed operation=finish request_id=%s status=%s",
                request_id,
                status.value,
            )


def _detail(
    *,
    headers: Mapping[str, str],
    body: Any | None,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    detail = dict(redact_json(metadata))
    if headers:
        detail["headers"] = redact_headers(headers)
    if body is not None:
        detail["body"] = _redacted_body(body)
    return detail


def _redacted_body(body: Any) -> Any:
    decoded: Any = body
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
        try:
            decoded = orjson.loads(text)
        except orjson.JSONDecodeError:
            decoded = text
    elif isinstance(body, str):
        try:
            decoded = orjson.loads(body)
        except orjson.JSONDecodeError:
            decoded = body
    return redact_json(decoded)


def _default_service() -> AuditService:
    return AuditService(
        get_session_factory(),
        body_limit_bytes=get_settings().audit_body_limit_bytes,
    )


async def start_request(context: RequestContext, body: bytes) -> UUID:
    try:
        service = _default_service()
    except Exception:
        request_id = uuid4()
        logger.exception(
            "Audit write failed operation=start request_id=%s",
            request_id,
        )
        return request_id
    return await service.start_request(context, body)


async def complete_request(request_id: UUID, result: RequestResult) -> None:
    try:
        service = _default_service()
    except Exception:
        logger.exception(
            "Audit write failed operation=finish request_id=%s status=%s",
            request_id,
            RequestStatus.COMPLETED.value,
        )
        return
    await service.complete_request(request_id, result)


async def fail_request(request_id: UUID, failure: RequestFailure) -> None:
    try:
        service = _default_service()
    except Exception:
        failure_status = (
            RequestStatus.CLIENT_DISCONNECTED
            if failure.client_disconnected
            else RequestStatus.FAILED
        )
        logger.exception(
            "Audit write failed operation=finish request_id=%s status=%s",
            request_id,
            failure_status.value,
        )
        return
    await service.fail_request(request_id, failure)
