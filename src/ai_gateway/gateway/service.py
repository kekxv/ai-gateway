from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import monotonic
from typing import Any
from typing import Protocol as TypingProtocol
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import orjson
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import ClientDisconnect
from starlette.types import Receive, Scope, Send

from ai_gateway.audit.service import (
    AuditService,
    RequestContext,
    RequestFailure,
    RequestResult,
)
from ai_gateway.auth.api_key import ApiKeyPrincipal, authenticate_api_key, extract_api_key
from ai_gateway.billing.pricing import calculate_cost
from ai_gateway.billing.service import (
    BalanceReservation,
    BillingService,
    IdempotencyConflict,
    ReservationRecovery,
    SettlementResult,
)
from ai_gateway.billing.usage import (
    UsageResult,
    estimate_request_tokens,
    resolve_usage,
)
from ai_gateway.catalog.repository import CatalogRepository
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import Protocol, UsageSource
from ai_gateway.core.errors import GatewayError
from ai_gateway.core.logging import current_request_id
from ai_gateway.db.models import Model
from ai_gateway.protocols.base import (
    UnsupportedFeatureError,
    is_object,
    rewrite_passthrough_request,
)
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.protocols.types import CanonicalRequest, CanonicalResponse, CanonicalUsage, TextPart
from ai_gateway.routing.service import router_for_settings
from ai_gateway.routing.types import NoRouteAvailable, RouteCandidate, RouteFailure
from ai_gateway.transport.sse import GatewayContext, stream_gateway_response
from ai_gateway.transport.upstream import build_upstream_request

logger = logging.getLogger(__name__)

_SAFE_NATIVE_ERROR_HEADERS = frozenset({"retry-after", "www-authenticate"})


class HttpClientProvider(TypingProtocol):
    async def client_for(self, url: str | httpx.URL) -> httpx.AsyncClient: ...


class RouteSelector(TypingProtocol):
    async def select_route(
        self,
        model: int,
        principal: ApiKeyPrincipal,
        required_protocol: Protocol | str | None = None,
        *,
        requested_model: str | None = None,
        excluded_route_ids: frozenset[int] | set[int] = frozenset(),
    ) -> RouteCandidate: ...

    async def record_success(self, route_id: int) -> bool: ...

    async def record_failure(self, route_id: int, failure: object) -> bool: ...


class InvalidRequestError(GatewayError):
    code = "invalid_request"
    status_code = 400


class UpstreamError(GatewayError):
    code = "upstream_error"
    status_code = 502

    def __init__(
        self,
        message: str,
        *,
        route: RouteCandidate | None = None,
        attempts: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.route = route
        self.attempts = attempts
        super().__init__(message)


class UpstreamTimeout(GatewayError):
    code = "upstream_timeout"
    status_code = 504

    def __init__(
        self,
        message: str,
        *,
        route: RouteCandidate | None = None,
        attempts: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.route = route
        self.attempts = attempts
        super().__init__(message)


class _RoutedGatewayError(GatewayError):
    def __init__(
        self,
        source: GatewayError,
        route: RouteCandidate,
        attempts: tuple[dict[str, Any], ...],
    ) -> None:
        self.code = source.code
        self.status_code = source.status_code
        self.route = route
        self.attempts = attempts
        super().__init__(source.message)


@dataclass(frozen=True, slots=True)
class GatewayOutput:
    body: bytes
    status_code: int
    content_type: str | None

    def response(self) -> Response:
        headers = {"content-type": self.content_type} if self.content_type is not None else None
        return Response(
            content=self.body,
            status_code=self.status_code,
            headers=headers,
        )


@dataclass(frozen=True, slots=True)
class GatewayStreamOutput:
    lifecycle: _StreamLifecycle
    status_code: int
    content_type: str = "text/event-stream"

    def response(self) -> StreamingResponse:
        return _GatewayStreamingResponse(
            self.lifecycle,
            status_code=self.status_code,
            headers={"content-type": self.content_type},
        )


@dataclass(frozen=True, slots=True)
class _PreparedRequest:
    raw_body: bytes
    payload: dict[str, Any]
    canonical: CanonicalRequest
    requested_model: str
    inbound_protocol: Protocol


@dataclass(frozen=True, slots=True)
class _AttemptResponse:
    route: RouteCandidate
    response: httpx.Response
    attempts: tuple[dict[str, Any], ...]
    router: RouteSelector


class GatewayService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        billing_service: BillingService,
        audit_service: AuditService,
        http_client_factory: HttpClientProvider,
        router_factory: Callable[[AsyncSession], RouteSelector] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._billing = billing_service
        self._audit = audit_service
        self._http_clients = http_client_factory
        self._router_factory = router_factory or (
            lambda active_session: router_for_settings(active_session, settings)
        )

    async def handle(
        self,
        request: Request,
        inbound_protocol: Protocol,
        *,
        path_model: str | None = None,
        force_stream: bool = False,
    ) -> GatewayOutput | GatewayStreamOutput:
        started_at = monotonic()

        # Authentication deliberately precedes parsing or catalog/database work.
        principal = await authenticate_api_key(extract_api_key(request), self._session)
        raw_body = await request.body()
        payload, requested_model = _request_payload(raw_body, inbound_protocol, path_model)
        if force_stream:
            payload["stream"] = True

        resolved = await CatalogRepository(self._session).resolve_model(requested_model)
        canonical = get_adapter(inbound_protocol).decode_request(payload)
        prepared = _PreparedRequest(
            raw_body,
            payload,
            canonical,
            requested_model,
            inbound_protocol,
        )

        priced_model = await self._session.get(Model, resolved.model_id)
        if priced_model is None:
            raise RuntimeError("resolved catalog model disappeared")
        request_id = uuid4()
        billing_key = _billing_key(principal, request_id)
        estimated_input_tokens = estimate_request_tokens(canonical)
        reservation = await self._billing.reserve_balance(
            user_id=principal.user_id,
            model=priced_model,
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=canonical.max_output_tokens,
            idempotency_key=billing_key,
            request_id=request_id,
            recovery=self._recovery_snapshot(
                billing_key,
                CanonicalUsage(0, 0),
                UsageSource.ESTIMATED,
                cost=Decimal("0"),
            ),
        )

        audit_id = uuid4()
        attempt_response: _AttemptResponse | None = None
        settled = False
        settled_cost = Decimal("0")
        pending_usage_result: UsageResult | None = None
        settled_usage_result: UsageResult | None = None
        audit_terminal = False
        try:
            correlation_id = _audit_correlation_id(request)
            audit_metadata = {
                "requested_model": requested_model,
                "canonical_model": resolved.canonical_name,
            }
            if correlation_id is not None:
                audit_metadata["client_request_id"] = correlation_id
            audit_id = await self._audit.start_request(
                RequestContext(
                    user_id=principal.user_id,
                    api_key_id=principal.api_key_id,
                    model_id=resolved.model_id,
                    inbound_protocol=inbound_protocol,
                    transport="http",
                    stream=canonical.stream,
                    headers=_audit_headers(request, correlation_id),
                    metadata=audit_metadata,
                ),
                raw_body,
                request_id=audit_id,
            )
            stream_context: GatewayContext | None = None
            stream_iterator: AsyncIterator[bytes] | None = None
            prefetched_frame: bytes | None = None
            if canonical.stream:
                (
                    attempt_response,
                    stream_context,
                    stream_iterator,
                    prefetched_frame,
                ) = await self._open_stream_with_prefetch(
                    request=request,
                    prepared=prepared,
                    principal=principal,
                    model_id=resolved.model_id,
                    inbound_protocol=inbound_protocol,
                    estimated_input_tokens=estimated_input_tokens,
                    started_at=started_at,
                )
                if stream_context is not None:
                    prefetched_usage = _stream_usage_result(
                        stream_context,
                        replace(canonical, model=attempt_response.route.upstream_model),
                    )
                    await self._persist_recovery(
                        reservation,
                        self._recovery_snapshot(
                            billing_key,
                            prefetched_usage.usage,
                            prefetched_usage.usage_source,
                            cost=calculate_cost(priced_model, prefetched_usage.usage),
                        ),
                    )
            else:
                attempt_response = await self._send_with_failover(
                    request=request,
                    prepared=prepared,
                    principal=principal,
                    model_id=resolved.model_id,
                )
            route = attempt_response.route
            upstream = attempt_response.response

            if upstream.status_code >= 400:
                if canonical.stream:
                    await upstream.aread()
                settlement = await self._settle_zero(reservation, billing_key)
                settled = True
                settled_cost = settlement.actual_cost
                output = _same_protocol_error_output(inbound_protocol, route, upstream)
                await self._audit.fail_request(
                    audit_id,
                    RequestFailure(
                        error_code="upstream_error",
                        provider_id=route.provider_id,
                        model_route_id=route.route_id,
                        outbound_protocol=route.protocol,
                        http_status=upstream.status_code,
                        cost=settlement.actual_cost,
                        latency_ms=_elapsed_ms(started_at),
                        headers=dict(upstream.headers),
                        body=upstream.content,
                        metadata={"attempts": attempt_response.attempts},
                    ),
                )
                audit_terminal = True
                if output is not None:
                    await upstream.aclose()
                    return output
                await upstream.aclose()
                raise UpstreamError("The upstream provider rejected the request")

            if canonical.stream:
                if stream_context is None or stream_iterator is None or prefetched_frame is None:
                    raise UpstreamError("The upstream provider returned an empty stream")
                lifecycle = _StreamLifecycle(
                    service=self,
                    context=stream_context,
                    upstream=upstream,
                    source=stream_iterator,
                    prefetched_frame=prefetched_frame,
                    request=replace(canonical, model=route.upstream_model),
                    reservation=reservation,
                    billing_key=billing_key,
                    audit_id=audit_id,
                    route=route,
                    attempts=attempt_response.attempts,
                    router=attempt_response.router,
                    priced_model=priced_model,
                    started_at=started_at,
                )
                return GatewayStreamOutput(
                    lifecycle=lifecycle,
                    status_code=upstream.status_code,
                    content_type=upstream.headers.get("content-type", "text/event-stream"),
                )

            output, response_payload, canonical_response = _convert_response(
                inbound_protocol=inbound_protocol,
                route=route,
                upstream=upstream,
            )
            usage_result = _resolve_response_usage(
                route=route,
                response_payload=response_payload,
                request=replace(canonical, model=route.upstream_model),
                canonical_response=canonical_response,
                response_body=upstream.content,
            )
            pending_usage_result = usage_result
            await self._persist_recovery(
                reservation,
                self._recovery_snapshot(
                    billing_key,
                    usage_result.usage,
                    usage_result.usage_source,
                    cost=calculate_cost(priced_model, usage_result.usage),
                ),
            )
            settlement = await self._billing.settle_request(
                reservation_id=reservation.ledger_entry_id,
                idempotency_key=billing_key,
                model=priced_model,
                usage=usage_result.usage,
                usage_source=usage_result.usage_source,
            )
            settled = True
            settled_cost = settlement.actual_cost
            settled_usage_result = usage_result
            await self._audit.complete_request(
                audit_id,
                RequestResult(
                    provider_id=route.provider_id,
                    model_route_id=route.route_id,
                    outbound_protocol=route.protocol,
                    http_status=output.status_code,
                    prompt_tokens=usage_result.usage.input_tokens,
                    completion_tokens=usage_result.usage.output_tokens,
                    usage_source=usage_result.usage_source,
                    cost=settlement.actual_cost,
                    latency_ms=_elapsed_ms(started_at),
                    headers=dict(upstream.headers),
                    body=output.body,
                    metadata={"attempts": attempt_response.attempts},
                ),
            )
            audit_terminal = True
            return output
        except BaseException as exc:
            if attempt_response is not None:
                await _close_response_auxiliary(
                    attempt_response.response,
                    attempt_response.route,
                    attempt_response.attempts,
                )
            final_route = (
                attempt_response.route
                if attempt_response is not None
                else getattr(exc, "route", None)
            )
            attempts = (
                attempt_response.attempts
                if attempt_response is not None
                else getattr(exc, "attempts", ())
            )
            await _run_cleanup_shielded(
                self._cleanup_after_failure(
                    reservation=reservation,
                    billing_key=billing_key,
                    audit_id=audit_id,
                    exc=exc,
                    final_route=final_route,
                    attempts=attempts,
                    settled=settled,
                    settled_cost=settled_cost,
                    priced_model=priced_model,
                    pending_usage_result=pending_usage_result,
                    settled_usage_result=settled_usage_result,
                    audit_terminal=audit_terminal,
                    started_at=started_at,
                )
            )
            raise

    async def _open_stream_with_prefetch(
        self,
        *,
        request: Request,
        prepared: _PreparedRequest,
        principal: ApiKeyPrincipal,
        model_id: int,
        inbound_protocol: Protocol,
        estimated_input_tokens: int,
        started_at: float,
    ) -> tuple[
        _AttemptResponse,
        GatewayContext | None,
        AsyncIterator[bytes] | None,
        bytes | None,
    ]:
        router = self._router_factory(self._session)
        attempted_route_ids: set[int] = set()
        attempts: list[dict[str, Any]] = []
        last_attempt: _AttemptResponse | None = None
        last_prefetch_failure: BaseException | None = None
        while True:
            try:
                attempt = await self._send_with_failover(
                    request=request,
                    prepared=prepared,
                    principal=principal,
                    model_id=model_id,
                    router=router,
                    attempted_route_ids=attempted_route_ids,
                    attempts=attempts,
                )
            except (UpstreamError, UpstreamTimeout) as exc:
                if last_attempt is not None:
                    if isinstance(last_prefetch_failure, httpx.TimeoutException):
                        raise UpstreamTimeout(
                            "The upstream provider timed out",
                            route=last_attempt.route,
                            attempts=tuple(attempts),
                        ) from last_prefetch_failure
                    exc.route = last_attempt.route
                    exc.attempts = tuple(attempts)
                raise
            if attempt.response.status_code >= 400:
                return attempt, None, None, None
            context = GatewayContext(
                source_protocol=attempt.route.protocol,
                target_protocol=inbound_protocol,
                initial_input_tokens=estimated_input_tokens,
                audit_body_limit_bytes=self._settings.audit_body_limit_bytes,
                started_at=started_at,
            )
            iterator = stream_gateway_response(context, attempt.response)
            try:
                first_frame = await anext(iterator)
            except asyncio.CancelledError:
                await _close_stream_iterator(iterator)
                raise
            except StopAsyncIteration:
                failure: BaseException = UpstreamError(
                    "The upstream provider returned an empty stream"
                )
            except BaseException as exc:
                failure = exc
            else:
                attempts[-1]["outcome"] = "success"
                return (
                    replace(attempt, attempts=tuple(attempts)),
                    context,
                    iterator,
                    first_frame,
                )

            retryable = is_retryable_failure(exception=failure) or isinstance(
                failure,
                (GatewayError, ValueError),
            )
            attempts[-1]["outcome"] = "failure"
            attempts[-1]["error_code"] = (
                "upstream_timeout"
                if isinstance(failure, httpx.TimeoutException)
                else "upstream_error"
            )
            attempt = replace(attempt, attempts=tuple(attempts))
            last_attempt = attempt
            last_prefetch_failure = failure
            await _close_stream_iterator(iterator)
            if not retryable:
                raise UpstreamError(
                    "The upstream provider returned an invalid stream",
                    route=attempt.route,
                    attempts=attempt.attempts,
                ) from failure
            health_failure = await _record_health_auxiliary(
                "record_failure",
                router.record_failure(
                    attempt.route.route_id,
                    RouteFailure(exception=failure),
                ),
                attempt.route,
                attempt.attempts,
            )
            if health_failure is not None:
                raise health_failure

    async def _finalize_stream(
        self,
        *,
        context: GatewayContext,
        upstream: httpx.Response,
        request: CanonicalRequest,
        reservation: BalanceReservation,
        billing_key: str,
        audit_id: UUID,
        route: RouteCandidate,
        attempts: tuple[dict[str, Any], ...],
        router: RouteSelector,
        priced_model: Model,
        started_at: float,
        completed: bool,
        terminal_error: BaseException | None,
        downstream_failed: bool = False,
    ) -> None:
        try:
            await upstream.aclose()
        except BaseException as cleanup_exc:
            _log_cleanup_failure("stream_response_close", cleanup_exc)

        usage_result = _stream_usage_result(context, request)
        settlement_cost = Decimal("0")
        billing_recovery_pending = False
        try:
            await self._persist_recovery(
                reservation,
                self._recovery_snapshot(
                    billing_key,
                    usage_result.usage,
                    usage_result.usage_source,
                    cost=calculate_cost(priced_model, usage_result.usage),
                ),
            )
            settlement = await self._billing.settle_request(
                reservation_id=reservation.ledger_entry_id,
                idempotency_key=billing_key,
                model=priced_model,
                usage=usage_result.usage,
                usage_source=usage_result.usage_source,
            )
            settlement_cost = settlement.actual_cost
        except BaseException as cleanup_exc:
            billing_recovery_pending = True
            _log_cleanup_failure("stream_settlement", cleanup_exc)

        disconnected = isinstance(
            terminal_error,
            (asyncio.CancelledError, GeneratorExit, ClientDisconnect, BrokenPipeError),
        )
        successful = completed and not context.error_observed
        effective_error = terminal_error
        if context.error_observed and effective_error is None:
            effective_error = UpstreamError("The upstream provider returned a stream error")
        try:
            if successful:
                await self._audit.complete_request(
                    audit_id,
                    RequestResult(
                        provider_id=route.provider_id,
                        model_route_id=route.route_id,
                        outbound_protocol=route.protocol,
                        http_status=upstream.status_code,
                        prompt_tokens=usage_result.usage.input_tokens,
                        completion_tokens=usage_result.usage.output_tokens,
                        usage_source=usage_result.usage_source,
                        cost=settlement_cost,
                        latency_ms=_elapsed_ms(started_at),
                        first_token_ms=context.first_token_ms,
                        headers=dict(upstream.headers),
                        body=context.audit_preview,
                        metadata={
                            "attempts": attempts,
                            "billing_recovery_pending": billing_recovery_pending,
                        },
                    ),
                )
            else:
                await self._audit.fail_request(
                    audit_id,
                    RequestFailure(
                        error_code=(
                            "client_disconnected"
                            if disconnected
                            else _public_error_code(
                                effective_error or UpstreamError("stream failed")
                            )
                        ),
                        client_disconnected=disconnected,
                        provider_id=route.provider_id,
                        model_route_id=route.route_id,
                        outbound_protocol=route.protocol,
                        http_status=upstream.status_code,
                        prompt_tokens=usage_result.usage.input_tokens,
                        completion_tokens=usage_result.usage.output_tokens,
                        usage_source=usage_result.usage_source,
                        cost=settlement_cost,
                        latency_ms=_elapsed_ms(started_at),
                        first_token_ms=context.first_token_ms,
                        headers=dict(upstream.headers),
                        body=context.audit_preview,
                        metadata={
                            "attempts": attempts,
                            "billing_recovery_pending": billing_recovery_pending,
                        },
                    ),
                )
        except BaseException as cleanup_exc:
            _log_cleanup_failure("stream_audit", cleanup_exc)

        if disconnected or downstream_failed:
            return
        health_operation = (
            router.record_success(route.route_id)
            if successful
            else router.record_failure(
                route.route_id,
                RouteFailure(exception=effective_error or RuntimeError("stream failed")),
            )
        )
        try:
            await health_operation
        except BaseException as cleanup_exc:
            _log_cleanup_failure("stream_health", cleanup_exc)

    async def _cleanup_after_failure(
        self,
        *,
        reservation: BalanceReservation,
        billing_key: str,
        audit_id: UUID,
        exc: BaseException,
        final_route: RouteCandidate | None,
        attempts: tuple[dict[str, Any], ...],
        settled: bool,
        settled_cost: Decimal,
        priced_model: Model,
        pending_usage_result: UsageResult | None,
        settled_usage_result: UsageResult | None,
        audit_terminal: bool,
        started_at: float,
    ) -> None:
        cleanup_cost = settled_cost
        charged_usage_result = settled_usage_result
        if not settled:
            try:
                if pending_usage_result is None:
                    cleanup_cost = (await self._settle_zero(reservation, billing_key)).actual_cost
                else:
                    recovered = await self._billing.settle_request(
                        reservation_id=reservation.ledger_entry_id,
                        idempotency_key=billing_key,
                        model=priced_model,
                        usage=pending_usage_result.usage,
                        usage_source=pending_usage_result.usage_source,
                    )
                    cleanup_cost = recovered.actual_cost
                    charged_usage_result = pending_usage_result
            except IdempotencyConflict:
                pass
            except BaseException as cleanup_exc:
                _log_cleanup_failure("settlement", cleanup_exc)
        if audit_terminal:
            return
        try:
            await self._audit.fail_request(
                audit_id,
                RequestFailure(
                    error_code=_public_error_code(exc),
                    client_disconnected=isinstance(exc, asyncio.CancelledError),
                    provider_id=(final_route.provider_id if final_route is not None else None),
                    model_route_id=(final_route.route_id if final_route is not None else None),
                    outbound_protocol=(final_route.protocol if final_route is not None else None),
                    http_status=getattr(exc, "status_code", None),
                    prompt_tokens=(
                        charged_usage_result.usage.input_tokens
                        if charged_usage_result is not None
                        else 0
                    ),
                    completion_tokens=(
                        charged_usage_result.usage.output_tokens
                        if charged_usage_result is not None
                        else 0
                    ),
                    usage_source=(
                        charged_usage_result.usage_source
                        if charged_usage_result is not None
                        else None
                    ),
                    cost=cleanup_cost,
                    latency_ms=_elapsed_ms(started_at),
                    metadata={
                        "attempts": attempts,
                        "billing_recovery_pending": (
                            pending_usage_result is not None and charged_usage_result is None
                        ),
                    },
                ),
            )
        except BaseException as cleanup_exc:
            _log_cleanup_failure("audit", cleanup_exc)

    async def _send_with_failover(
        self,
        *,
        request: Request,
        prepared: _PreparedRequest,
        principal: ApiKeyPrincipal,
        model_id: int,
        router: RouteSelector | None = None,
        attempted_route_ids: set[int] | None = None,
        attempts: list[dict[str, Any]] | None = None,
    ) -> _AttemptResponse:
        router = router or self._router_factory(self._session)
        attempted_route_ids = attempted_route_ids if attempted_route_ids is not None else set()
        attempts = attempts if attempts is not None else []
        last_failure: BaseException | httpx.Response | None = None
        last_route: RouteCandidate | None = None

        while True:
            try:
                route = await router.select_route(
                    model_id,
                    principal,
                    requested_model=prepared.requested_model,
                    excluded_route_ids=attempted_route_ids,
                )
            except NoRouteAvailable:
                if not attempts:
                    raise
                if isinstance(last_failure, httpx.TimeoutException):
                    raise UpstreamTimeout(
                        "The upstream provider timed out",
                        route=last_route,
                        attempts=tuple(attempts),
                    ) from last_failure
                raise UpstreamError(
                    "No upstream provider completed the request",
                    route=last_route,
                    attempts=tuple(attempts),
                )

            attempted_route_ids.add(route.route_id)
            last_route = route
            try:
                body = _upstream_body(prepared, route)
                url = upstream_url(
                    route.protocol,
                    route.base_url,
                    route.upstream_model,
                    stream=prepared.canonical.stream,
                )
                upstream_request = build_upstream_request(
                    route,
                    request.headers,
                    body,
                    settings=self._settings,
                    url=url,
                )
            except UnsupportedFeatureError as exc:
                raise _RoutedGatewayError(exc, route, tuple(attempts)) from exc
            except Exception as exc:
                raise UpstreamError(
                    "The upstream request could not be prepared",
                    route=route,
                    attempts=tuple(attempts),
                ) from exc
            try:
                client = await self._http_clients.client_for(url)
                upstream = await client.send(
                    upstream_request,
                    stream=prepared.canonical.stream,
                )
            except asyncio.CancelledError as exc:
                _annotate_failure(exc, route, tuple(attempts))
                raise
            except Exception as exc:
                if not is_retryable_failure(exception=exc):
                    raise UpstreamError(
                        "The upstream request failed",
                        route=route,
                        attempts=tuple(attempts),
                    ) from exc
                attempts.append(_attempt_summary(route, len(attempts) + 1, exception=exc))
                last_failure = exc
                health_failure = await _record_health_auxiliary(
                    "record_failure",
                    router.record_failure(route.route_id, RouteFailure(exception=exc)),
                    route,
                    tuple(attempts),
                )
                if health_failure is not None:
                    raise health_failure
                continue

            if is_retryable_failure(status_code=upstream.status_code):
                attempts.append(
                    _attempt_summary(
                        route,
                        len(attempts) + 1,
                        status_code=upstream.status_code,
                    )
                )
                last_failure = upstream
                health_failure = await _record_health_auxiliary(
                    "record_failure",
                    router.record_failure(route.route_id, upstream.status_code),
                    route,
                    tuple(attempts),
                )
                close_failure = await _close_response_auxiliary(
                    upstream,
                    route,
                    tuple(attempts),
                )
                if health_failure is not None:
                    raise health_failure
                if close_failure is not None:
                    raise close_failure
                continue

            summary = _attempt_summary(
                route,
                len(attempts) + 1,
                status_code=upstream.status_code,
                succeeded=upstream.status_code < 400,
            )
            if prepared.canonical.stream and upstream.status_code < 400:
                summary["outcome"] = "pending"
            attempts.append(summary)
            if prepared.canonical.stream and upstream.status_code < 400:
                return _AttemptResponse(route, upstream, tuple(attempts), router)
            health_operation = (
                router.record_failure(route.route_id, upstream.status_code)
                if upstream.status_code >= 400
                else router.record_success(route.route_id)
            )
            health_failure = await _record_health_auxiliary(
                "record_failure" if upstream.status_code >= 400 else "record_success",
                health_operation,
                route,
                tuple(attempts),
            )
            if health_failure is not None:
                await _close_response_auxiliary(upstream, route, tuple(attempts))
                raise health_failure
            return _AttemptResponse(route, upstream, tuple(attempts), router)

    async def _settle_zero(
        self,
        reservation: BalanceReservation,
        billing_key: str,
    ) -> SettlementResult:
        return await self._billing.settle_request(
            reservation_id=reservation.ledger_entry_id,
            idempotency_key=billing_key,
            cost=Decimal("0"),
        )

    def _recovery_snapshot(
        self,
        billing_key: str,
        usage: CanonicalUsage,
        usage_source: UsageSource,
        *,
        cost: Decimal,
    ) -> ReservationRecovery:
        return ReservationRecovery(
            settlement_key=billing_key,
            usage=usage,
            usage_source=usage_source,
            expires_at=datetime.now(UTC).replace(tzinfo=None)
            + timedelta(seconds=self._settings.billing_reservation_ttl_seconds),
            cost=cost,
        )

    async def _persist_recovery(
        self,
        reservation: BalanceReservation | None,
        recovery: ReservationRecovery | None,
    ) -> None:
        if reservation is None or recovery is None:
            return
        updater = getattr(self._billing, "update_reservation_recovery", None)
        if updater is None:
            return
        try:
            await updater(
                reservation_id=reservation.ledger_entry_id,
                recovery=recovery,
            )
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            _log_cleanup_failure("reservation_recovery_update", exc)


class _StreamLifecycle:
    def __init__(
        self,
        *,
        service: GatewayService,
        context: GatewayContext,
        upstream: httpx.Response,
        source: AsyncIterator[bytes],
        prefetched_frame: bytes,
        request: CanonicalRequest,
        reservation: BalanceReservation,
        billing_key: str,
        audit_id: UUID,
        route: RouteCandidate,
        attempts: tuple[dict[str, Any], ...],
        router: RouteSelector,
        priced_model: Model,
        started_at: float,
    ) -> None:
        self.context = context
        self._service = service
        self._upstream = upstream
        self._source = source
        self._prefetched_frame = prefetched_frame
        self._request = request
        self._reservation = reservation
        self._billing_key = billing_key
        self._audit_id = audit_id
        self._route = route
        self._attempts = attempts
        self._router = router
        self._priced_model = priced_model
        self._started_at = started_at
        self._completed = False
        self._terminal_error: BaseException | None = None
        self._downstream_failed = False
        self._finalize_lock = asyncio.Lock()
        self._finalize_task: asyncio.Task[None] | None = None

    def iterator(self) -> _StreamLifecycleIterator:
        return _StreamLifecycleIterator(self)

    def mark_completed(self) -> None:
        self._completed = True

    def note_error(self, exc: BaseException, *, downstream: bool = False) -> None:
        if self._terminal_error is None:
            self._terminal_error = exc
        self._downstream_failed = self._downstream_failed or downstream

    async def next_source(self) -> bytes:
        if self._prefetched_frame:
            frame = self._prefetched_frame
            self._prefetched_frame = b""
            return frame
        frame = await anext(self._source)
        usage_result = _stream_usage_result(self.context, self._request)
        await self._service._persist_recovery(
            self._reservation,
            self._service._recovery_snapshot(
                self._billing_key,
                usage_result.usage,
                usage_result.usage_source,
                cost=calculate_cost(self._priced_model, usage_result.usage),
            ),
        )
        return frame

    async def finalize_once(self) -> None:
        async with self._finalize_lock:
            if self._finalize_task is None:
                if not self._completed and self._terminal_error is None:
                    self._terminal_error = GeneratorExit()
                self._finalize_task = asyncio.create_task(self._finalize())
            task = self._finalize_task
        while True:
            try:
                await asyncio.shield(task)
                return
            except asyncio.CancelledError:
                if task.done():
                    return

    async def _finalize(self) -> None:
        await _close_stream_iterator(self._source)
        await self._service._finalize_stream(
            context=self.context,
            upstream=self._upstream,
            request=self._request,
            reservation=self._reservation,
            billing_key=self._billing_key,
            audit_id=self._audit_id,
            route=self._route,
            attempts=self._attempts,
            router=self._router,
            priced_model=self._priced_model,
            started_at=self._started_at,
            completed=self._completed,
            terminal_error=self._terminal_error,
            downstream_failed=self._downstream_failed,
        )


class _StreamLifecycleIterator:
    def __init__(self, lifecycle: _StreamLifecycle) -> None:
        self._lifecycle = lifecycle

    def __aiter__(self) -> _StreamLifecycleIterator:
        return self

    async def __anext__(self) -> bytes:
        try:
            return await self._lifecycle.next_source()
        except StopAsyncIteration:
            self._lifecycle.mark_completed()
            await self._lifecycle.finalize_once()
            raise
        except BaseException as exc:
            self._lifecycle.note_error(exc)
            await self._lifecycle.finalize_once()
            raise

    async def aclose(self) -> None:
        self._lifecycle.note_error(GeneratorExit())
        await self._lifecycle.finalize_once()


class _GatewayStreamingResponse(StreamingResponse):
    def __init__(self, lifecycle: _StreamLifecycle, **kwargs: Any) -> None:
        self._lifecycle = lifecycle
        super().__init__(lifecycle.iterator(), **kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except BaseException as exc:
            self._lifecycle.note_error(exc, downstream=True)
            raise
        finally:
            await self._lifecycle.finalize_once()


def upstream_url(
    protocol: Protocol | str,
    base_url: str,
    upstream_model: str,
    *,
    stream: bool = False,
) -> str:
    selected = Protocol(protocol)
    base = base_url.rstrip("/")
    if selected is Protocol.OPENAI:
        return f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
    if selected is Protocol.CLAUDE:
        return f"{base}/messages" if base.endswith("/v1") else f"{base}/v1/messages"
    encoded_model = quote(upstream_model.removeprefix("models/"), safe="")
    prefix = base if base.endswith("/v1beta") else f"{base}/v1beta"
    method = "streamGenerateContent?alt=sse" if stream else "generateContent"
    return f"{prefix}/models/{encoded_model}:{method}"


def is_retryable_failure(
    *,
    status_code: int | None = None,
    exception: BaseException | None = None,
) -> bool:
    if status_code is not None:
        return status_code in {408, 429} or 500 <= status_code <= 599
    return isinstance(exception, (httpx.NetworkError, httpx.TimeoutException, ConnectionError))


def _request_payload(
    raw_body: bytes,
    protocol: Protocol,
    path_model: str | None,
) -> tuple[dict[str, Any], str]:
    try:
        payload = orjson.loads(raw_body)
    except (UnicodeDecodeError, orjson.JSONDecodeError):
        raise InvalidRequestError("Request body must contain valid JSON") from None
    if not is_object(payload):
        raise InvalidRequestError("Request body must be a JSON object")
    model = path_model if protocol is Protocol.GEMINI else payload.get("model")
    if not isinstance(model, str) or not model.strip():
        raise InvalidRequestError("A non-empty model is required")
    normalized_model = model.removeprefix("models/") if protocol is Protocol.GEMINI else model
    payload = payload.copy()
    payload["model"] = normalized_model
    return payload, normalized_model


def _upstream_body(prepared: _PreparedRequest, route: RouteCandidate) -> bytes:
    if route.protocol is prepared.inbound_protocol:
        if route.protocol is Protocol.GEMINI:
            payload = prepared.payload.copy()
            payload.pop("model", None)
            payload.pop("stream", None)
            return orjson.dumps(payload)
        rewritten = rewrite_passthrough_request(
            route.protocol,
            orjson.dumps(prepared.payload),
            route.upstream_model,
        )
        return rewritten
    canonical = replace(prepared.canonical, model=route.upstream_model)
    payload = get_adapter(route.protocol).encode_request(canonical)
    if route.protocol is Protocol.GEMINI:
        payload.pop("model", None)
        payload.pop("stream", None)
    elif route.protocol is Protocol.OPENAI and prepared.canonical.stream:
        stream_options = payload.get("stream_options")
        if not isinstance(stream_options, dict):
            stream_options = {}
            payload["stream_options"] = stream_options
        stream_options["include_usage"] = True
    return orjson.dumps(payload)


def _convert_response(
    *,
    inbound_protocol: Protocol,
    route: RouteCandidate,
    upstream: httpx.Response,
) -> tuple[GatewayOutput, dict[str, Any], CanonicalResponse | None]:
    content_type = upstream.headers.get("content-type")
    payload = _json_object_or_empty(upstream.content)
    source_adapter = get_adapter(route.protocol)
    canonical_response: CanonicalResponse | None = None
    if route.protocol is inbound_protocol:
        try:
            canonical_response = source_adapter.decode_response(payload)
        except (GatewayError, ValueError):
            canonical_response = None
        return (
            GatewayOutput(upstream.content, upstream.status_code, content_type),
            payload,
            canonical_response,
        )

    try:
        canonical_response = source_adapter.decode_response(payload)
    except (GatewayError, ValueError) as exc:
        raise UpstreamError("The upstream provider returned an invalid response") from exc
    try:
        encoded = get_adapter(inbound_protocol).encode_response(canonical_response)
    except UnsupportedFeatureError:
        raise
    return (
        GatewayOutput(orjson.dumps(encoded), upstream.status_code, "application/json"),
        payload,
        canonical_response,
    )


def _resolve_response_usage(
    *,
    route: RouteCandidate,
    response_payload: Mapping[str, Any],
    request: CanonicalRequest,
    canonical_response: CanonicalResponse | None,
    response_body: bytes,
) -> UsageResult:
    response_text = _canonical_response_text(canonical_response)
    if not response_text:
        response_text = response_body.decode("utf-8", errors="replace")
    try:
        return resolve_usage(
            protocol=route.protocol,
            payload=response_payload,
            request=request,
            response_text=response_text,
        )
    except (GatewayError, ValueError):
        return resolve_usage(
            protocol=route.protocol,
            payload={},
            request=request,
            response_text=response_text,
        )


def _stream_usage_result(context: GatewayContext, request: CanonicalRequest) -> UsageResult:
    if context.provider_usage_complete and context.observed_usage is not None:
        return UsageResult(context.observed_usage, UsageSource.PROVIDER)
    return UsageResult(
        usage=(
            context.estimated_usage()
            if context.initial_input_tokens is not None or context.observed_usage is not None
            else CanonicalUsage(
                input_tokens=estimate_request_tokens(request),
                output_tokens=context.estimated_output_tokens,
            )
        ),
        usage_source=UsageSource.ESTIMATED,
    )


def _canonical_response_text(response: CanonicalResponse | None) -> str:
    if response is None:
        return ""
    return "".join(part.text for part in response.message.content if isinstance(part, TextPart))


def _json_object_or_empty(body: bytes) -> dict[str, Any]:
    try:
        payload = orjson.loads(body)
    except (UnicodeDecodeError, orjson.JSONDecodeError):
        return {}
    return payload if is_object(payload) else {}


def _same_protocol_error_output(
    inbound_protocol: Protocol,
    route: RouteCandidate,
    response: httpx.Response,
) -> GatewayOutput | None:
    if route.protocol is not inbound_protocol:
        return None
    return GatewayOutput(
        response.content,
        response.status_code,
        response.headers.get("content-type"),
    )


def _attempt_summary(
    route: RouteCandidate,
    attempt: int,
    *,
    status_code: int | None = None,
    exception: BaseException | None = None,
    succeeded: bool = False,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "attempt": attempt,
        "route_id": route.route_id,
        "provider_id": route.provider_id,
        "protocol": route.protocol.value,
        "outcome": "success" if succeeded else "failure",
    }
    if status_code is not None:
        summary["http_status"] = status_code
    if exception is not None:
        summary["error_code"] = (
            "upstream_timeout"
            if isinstance(exception, httpx.TimeoutException)
            else "upstream_error"
        )
    return summary


def _billing_key(principal: ApiKeyPrincipal, request_id: UUID) -> str:
    return f"gateway:{principal.user_id}:{principal.api_key_id}:{request_id}"


def _audit_correlation_id(request: Request) -> str | None:
    value = request.headers.get("x-request-id")
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 128:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        return None
    return normalized


def _audit_headers(request: Request, correlation_id: str | None) -> dict[str, str]:
    headers = dict(request.headers)
    headers.pop("idempotency-key", None)
    headers.pop("x-request-id", None)
    if correlation_id is not None:
        headers["x-request-id"] = correlation_id
    return headers


async def _run_cleanup_shielded(cleanup: Coroutine[Any, Any, None]) -> None:
    cleanup_task = asyncio.create_task(cleanup)
    while True:
        try:
            await asyncio.shield(cleanup_task)
            return
        except asyncio.CancelledError:
            if cleanup_task.done():
                return


async def _record_health_auxiliary(
    operation: str,
    mutation: Awaitable[bool],
    route: RouteCandidate,
    attempts: tuple[dict[str, Any], ...],
) -> BaseException | None:
    try:
        await mutation
    except asyncio.CancelledError as exc:
        _annotate_failure(exc, route, attempts)
        return exc
    except Exception as exc:
        _log_auxiliary_failure(operation, exc)
    except BaseException as exc:
        _annotate_failure(exc, route, attempts)
        return exc
    return None


async def _close_response_auxiliary(
    response: httpx.Response,
    route: RouteCandidate,
    attempts: tuple[dict[str, Any], ...],
) -> BaseException | None:
    close_task = asyncio.create_task(response.aclose())
    pending_cancellation: asyncio.CancelledError | None = None
    while True:
        try:
            await asyncio.shield(close_task)
            break
        except asyncio.CancelledError as exc:
            pending_cancellation = pending_cancellation or exc
            if close_task.done():
                break
        except Exception as exc:
            _log_auxiliary_failure("response_close", exc)
            return pending_cancellation
        except BaseException as exc:
            _annotate_failure(exc, route, attempts)
            return pending_cancellation or exc
    if pending_cancellation is not None:
        _annotate_failure(pending_cancellation, route, attempts)
    return pending_cancellation


async def _close_stream_iterator(iterator: AsyncIterator[bytes]) -> None:
    close = getattr(iterator, "aclose", None)
    if close is None:
        return
    try:
        await close()
    except BaseException as exc:
        _log_cleanup_failure("stream_iterator_close", exc)


def _annotate_failure(
    exc: BaseException,
    route: RouteCandidate,
    attempts: tuple[dict[str, Any], ...],
) -> None:
    setattr(exc, "route", route)
    setattr(exc, "attempts", attempts)


def _log_cleanup_failure(operation: str, exc: BaseException) -> None:
    logger.error(
        "Gateway cleanup failed operation=%s exception_type=%s",
        operation,
        type(exc).__name__,
    )


def _log_auxiliary_failure(operation: str, exc: BaseException) -> None:
    logger.warning(
        "Gateway auxiliary operation failed operation=%s exception_type=%s",
        operation,
        type(exc).__name__,
    )


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((monotonic() - started_at) * 1000))


def _public_error_code(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) else "upstream_error"


def native_error_response(protocol: Protocol, exc: BaseException) -> JSONResponse:
    status_code, code, message, include_request_id = _native_error_detail(exc)
    request_id = current_request_id() or ""
    if protocol is Protocol.OPENAI:
        error_type = (
            "authentication_error"
            if code == "invalid_api_key"
            else ("server_error" if status_code >= 500 else "invalid_request_error")
        )
        error: dict[str, Any] = {"message": message, "type": error_type, "code": code}
        if include_request_id:
            error["request_id"] = request_id
        content: dict[str, Any] = {"error": error}
    elif protocol is Protocol.CLAUDE:
        content = {"type": "error", "error": {"type": code, "message": message}}
        if include_request_id:
            content["request_id"] = request_id
    else:
        error = {
            "code": status_code,
            "message": message,
            "status": _gemini_status(status_code, code),
        }
        if include_request_id:
            error["request_id"] = request_id
        content = {"error": error}
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=_safe_native_error_headers(exc),
    )


def _native_error_detail(exc: BaseException) -> tuple[int, str, str, bool]:
    if isinstance(exc, (GatewayError, HTTPException)):
        status_code, code, message = _error_detail(exc)
        return status_code, code, message, False
    if isinstance(exc, SQLAlchemyError):
        _log_native_exception("Database gateway request failed", exc)
        return (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "database_unavailable",
            "Database unavailable",
            True,
        )
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        _log_native_exception("Gateway request timed out", exc)
        return status.HTTP_504_GATEWAY_TIMEOUT, "timeout", "Request timed out", True
    _log_native_exception("Unhandled gateway exception", exc)
    return status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Internal server error", True


def _log_native_exception(event: str, exc: BaseException) -> None:
    logger.exception(
        event,
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"exception_class": type(exc).__name__},
    )


def _safe_native_error_headers(exc: BaseException) -> dict[str, str] | None:
    if not isinstance(exc, HTTPException) or exc.headers is None:
        return None
    headers = {
        name: value
        for name, value in exc.headers.items()
        if name.lower() in _SAFE_NATIVE_ERROR_HEADERS
    }
    return headers or None


def _error_detail(exc: BaseException) -> tuple[int, str, str]:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        raw_code = detail.get("code") if isinstance(detail, Mapping) else None
        raw_message = detail.get("message") if isinstance(detail, Mapping) else None
        code = raw_code if isinstance(raw_code, str) else "invalid_api_key"
        if code in {"authentication_required", "ambiguous_credentials", "user_disabled"}:
            code = "invalid_api_key"
        message = raw_message if isinstance(raw_message, str) else "Invalid API key"
        return exc.status_code, code, message
    if isinstance(exc, GatewayError):
        return exc.status_code, exc.code, exc.message
    return status.HTTP_500_INTERNAL_SERVER_ERROR, "upstream_error", "The gateway request failed"


def _gemini_status(status_code: int, code: str) -> str:
    if code in {"timeout", "upstream_timeout"}:
        return "DEADLINE_EXCEEDED"
    if status_code == 400:
        return "INVALID_ARGUMENT"
    if status_code == 401:
        return "UNAUTHENTICATED"
    if status_code == 402 or status_code == 429:
        return "RESOURCE_EXHAUSTED"
    if status_code == 403:
        return "PERMISSION_DENIED"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 422:
        return "FAILED_PRECONDITION"
    if status_code == 503:
        return "UNAVAILABLE"
    return "INTERNAL"
