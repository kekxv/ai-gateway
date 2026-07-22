from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from time import monotonic
from typing import Annotated, Any, cast
from typing import Protocol as TypingProtocol
from uuid import UUID, uuid4

import anyio
import orjson
from fastapi import APIRouter, Depends, HTTPException, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.audit.service import AuditService, RequestContext, RequestFailure, RequestResult
from ai_gateway.auth.api_key import ApiKeyPrincipal, authenticate_api_key, extract_api_key
from ai_gateway.billing.pricing import PricedModel
from ai_gateway.billing.service import (
    BalanceReservation,
    BillingService,
    InsufficientBalance,
    SettlementResult,
)
from ai_gateway.billing.usage import UsageResult, estimate_text_tokens
from ai_gateway.catalog.repository import CatalogRepository
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol, UsageSource
from ai_gateway.db.models import Model
from ai_gateway.db.session import get_session
from ai_gateway.protocols.types import CanonicalUsage
from ai_gateway.routing.service import Router
from ai_gateway.routing.types import NoRouteAvailable, RouteCandidate, RouteFailure
from ai_gateway.transport.websocket import (
    Frame,
    RelayAbort,
    RelayResult,
    UpstreamWebSocketError,
    relay_websocket,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class BillingBackend(TypingProtocol):
    default_max_output_tokens: int

    async def reserve_balance(
        self,
        *,
        user_id: int,
        model: PricedModel,
        estimated_input_tokens: int,
        max_output_tokens: int | None,
        idempotency_key: str,
        request_id: UUID | str | None = None,
    ) -> BalanceReservation: ...

    async def settle_request(
        self,
        *,
        reservation_id: int,
        idempotency_key: str,
        model: PricedModel | None = None,
        usage: CanonicalUsage | None = None,
        cost: Decimal | None = None,
        usage_source: UsageSource | None = None,
    ) -> SettlementResult: ...


class RouteSelector(TypingProtocol):
    async def select_route(
        self,
        model: object,
        principal: ApiKeyPrincipal,
        required_protocol: Protocol | str | None = None,
        *,
        requested_model: str | None = None,
        excluded_route_ids: frozenset[int] | set[int] = frozenset(),
        require_websocket: bool = False,
    ) -> RouteCandidate: ...

    async def record_success(self, route_id: int) -> bool: ...

    async def record_failure(self, route_id: int, failure: object) -> bool: ...


@dataclass(frozen=True, slots=True)
class _GatewayClose(Exception):
    code: int
    error_code: str


class WebSocketUsage:
    """Track cumulative provider usage, falling back to frame metadata estimates."""

    def __init__(self, protocol: Protocol) -> None:
        self.protocol = protocol
        self._estimated_input = 0
        self._estimated_output = 0
        self._native_input: int | None = None
        self._native_output: int | None = None

    def observe_client(self, frame: Frame) -> None:
        self._estimated_input += estimate_websocket_frame_tokens(frame)

    def observe_upstream(self, frame: Frame) -> None:
        self._estimated_output += estimate_websocket_frame_tokens(frame)
        native = _native_usage(self.protocol, frame)
        if native is not None:
            self._native_input = max(self._native_input or 0, native.input_tokens)
            self._native_output = max(self._native_output or 0, native.output_tokens)

    def snapshot(self) -> UsageResult:
        if self._native_input is not None and self._native_output is not None:
            return UsageResult(
                CanonicalUsage(self._native_input, self._native_output),
                UsageSource.PROVIDER,
            )
        return UsageResult(
            CanonicalUsage(self._estimated_input, self._estimated_output),
            UsageSource.ESTIMATED,
        )


class WebSocketBillingCycle:
    """Settle and renew reservations throughout a long-running socket."""

    def __init__(
        self,
        *,
        billing: BillingBackend,
        user_id: int,
        model: PricedModel,
        billing_key: str,
        usage: WebSocketUsage,
        max_output_tokens: int,
        token_threshold: int = 100_000,
        interval_seconds: float = 60,
    ) -> None:
        self._billing = billing
        self._user_id = user_id
        self._model = model
        self._billing_key = billing_key
        self._usage = usage
        self._max_output_tokens = max_output_tokens
        self._token_threshold = token_threshold
        self._interval_seconds = interval_seconds
        self._reservation: BalanceReservation | None = None
        self._settled_usage = CanonicalUsage(0, 0)
        self._sequence = 0
        self._last_checkpoint = monotonic()
        self._finalized = False
        self._lock = anyio.Lock()
        self.actual_cost = Decimal("0")

    @property
    def has_open_reservation(self) -> bool:
        return self._reservation is not None

    async def reserve_initial(self, *, estimated_input_tokens: int) -> None:
        async with self._lock:
            if self._reservation is not None:
                return
            self._reservation = await self._reserve(estimated_input_tokens)

    async def checkpoint(self, *, force_time: bool = False) -> bool:
        async with self._lock:
            if self._finalized or self._reservation is None:
                return False
            current = self._usage.snapshot()
            delta = _usage_delta(current.usage, self._settled_usage)
            elapsed = monotonic() - self._last_checkpoint
            if not force_time and _total_tokens(delta) < self._token_threshold:
                if elapsed < self._interval_seconds:
                    return False
            settlement = await self._settle(self._reservation, delta, current.usage_source)
            self._reservation = None
            self.actual_cost += settlement.actual_cost
            self._settled_usage = current.usage
            self._last_checkpoint = monotonic()
            if settlement.exhausted:
                raise InsufficientBalance(required=Decimal("0.00000001"), available=Decimal("0"))
            self._reservation = await self._reserve(0)
            return True

    async def finalize(self) -> None:
        async with self._lock:
            if self._finalized:
                return
            if self._reservation is not None:
                current = self._usage.snapshot()
                delta = _usage_delta(current.usage, self._settled_usage)
                settlement = await self._settle(
                    self._reservation,
                    delta,
                    current.usage_source,
                )
                self.actual_cost += settlement.actual_cost
                self._reservation = None
                self._settled_usage = current.usage
            self._finalized = True

    async def _reserve(self, estimated_input_tokens: int) -> BalanceReservation:
        sequence = self._sequence
        self._sequence += 1
        return await self._billing.reserve_balance(
            user_id=self._user_id,
            model=self._model,
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=self._max_output_tokens,
            idempotency_key=f"{self._billing_key}:reserve:{sequence}",
            request_id=uuid4(),
        )

    async def _settle(
        self,
        reservation: BalanceReservation,
        usage: CanonicalUsage,
        usage_source: UsageSource,
    ) -> SettlementResult:
        return await self._billing.settle_request(
            reservation_id=reservation.ledger_entry_id,
            idempotency_key=f"{self._billing_key}:settle:{self._sequence - 1}",
            model=self._model,
            usage=usage,
            usage_source=usage_source,
        )


class WebSocketGatewayService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        billing_service: BillingBackend,
        audit_service: AuditService,
        router_factory: Callable[[AsyncSession], RouteSelector] = cast(
            Callable[[AsyncSession], RouteSelector], Router
        ),
    ) -> None:
        self._session = session
        self._settings = settings
        self._billing = billing_service
        self._audit = audit_service
        self._router_factory = router_factory

    async def handle(self, websocket: WebSocket, protocol: Protocol) -> None:
        await websocket.accept()
        started_at = monotonic()
        audit_id: UUID | None = None
        route: RouteCandidate | None = None
        route_router: RouteSelector | None = None
        billing_cycle: WebSocketBillingCycle | None = None
        usage = WebSocketUsage(protocol)
        result: RelayResult | None = None
        try:
            principal = await authenticate_api_key(
                extract_api_key(cast(Any, websocket)),
                self._session,
            )
            initial_request, requested_model = await _initial_request_and_model(websocket, protocol)
            resolved = await CatalogRepository(self._session).resolve_model(requested_model)
            route_router = self._router_factory(self._session)
            route = await route_router.select_route(
                resolved,
                principal,
                protocol,
                requested_model=requested_model,
                require_websocket=True,
            )
            priced_model = await self._session.get(Model, resolved.model_id)
            if priced_model is None:
                raise RuntimeError("resolved catalog model disappeared")

            request_id = uuid4()
            billing_key = f"websocket:{principal.user_id}:{principal.api_key_id}:{request_id}"
            audit_id = await self._audit.start_request(
                RequestContext(
                    user_id=principal.user_id,
                    api_key_id=principal.api_key_id,
                    model_id=resolved.model_id,
                    inbound_protocol=protocol,
                    transport="websocket",
                    stream=True,
                    headers=dict(websocket.headers),
                    metadata={
                        "requested_model": requested_model,
                        "canonical_model": resolved.canonical_name,
                    },
                ),
                _frame_bytes(initial_request),
                request_id=request_id,
            )
            billing_cycle = WebSocketBillingCycle(
                billing=self._billing,
                user_id=principal.user_id,
                model=priced_model,
                billing_key=billing_key,
                usage=usage,
                max_output_tokens=self._billing.default_max_output_tokens,
            )
            await billing_cycle.reserve_initial(
                estimated_input_tokens=estimate_websocket_frame_tokens(initial_request)
            )

            async def observe(direction: str, frame: Frame) -> None:
                if direction == "client":
                    usage.observe_client(frame)
                else:
                    usage.observe_upstream(frame)
                try:
                    await billing_cycle.checkpoint()
                except InsufficientBalance:
                    raise RelayAbort(4402, _close_reason("insufficient_balance")) from None

            async def interval() -> None:
                try:
                    await billing_cycle.checkpoint(force_time=True)
                except InsufficientBalance:
                    raise RelayAbort(4402, _close_reason("insufficient_balance")) from None

            result = await relay_websocket(
                cast(Any, websocket),
                route,
                initial_request,
                settings=self._settings,
                query_string=websocket.url.query,
                observe_frame=observe,
                on_interval=interval,
            )
            if result.upstream_failed:
                await _safe_health(
                    route_router.record_failure(
                        route.route_id,
                        RouteFailure(exception=result.exception),
                    )
                )
            else:
                await _safe_health(route_router.record_success(route.route_id))
        except BaseException as exc:
            if isinstance(exc, anyio.get_cancelled_exc_class()):
                raise
            if (
                route is not None
                and route_router is not None
                and isinstance(exc, UpstreamWebSocketError)
            ):
                await _safe_health(
                    route_router.record_failure(route.route_id, RouteFailure(exception=exc))
                )
            close = _gateway_close(exc)
            await _safe_close(websocket, close.code, _close_reason(close.error_code))
            result = RelayResult(
                client_disconnected=False,
                upstream_failed=isinstance(exc, UpstreamWebSocketError),
                close_code=close.code,
                close_reason=_close_reason(close.error_code),
                exception=exc,
            )
        finally:
            with anyio.CancelScope(shield=True):
                if billing_cycle is not None:
                    try:
                        await billing_cycle.finalize()
                    except Exception as exc:
                        logger.error(
                            "WebSocket billing cleanup failed exception_type=%s",
                            type(exc).__name__,
                        )
                if audit_id is not None:
                    usage_result = usage.snapshot()
                    cost = billing_cycle.actual_cost if billing_cycle is not None else Decimal("0")
                    if result is not None and (
                        result.client_disconnected
                        or result.exception is not None
                        or result.close_code not in {1000, 1001}
                    ):
                        await self._audit.fail_request(
                            audit_id,
                            RequestFailure(
                                error_code=_result_error_code(result),
                                client_disconnected=result.client_disconnected,
                                provider_id=route.provider_id if route is not None else None,
                                model_route_id=route.route_id if route is not None else None,
                                outbound_protocol=route.protocol if route is not None else None,
                                prompt_tokens=usage_result.usage.input_tokens,
                                completion_tokens=usage_result.usage.output_tokens,
                                usage_source=usage_result.usage_source,
                                cost=cost,
                                latency_ms=_elapsed_ms(started_at),
                            ),
                        )
                    else:
                        await self._audit.complete_request(
                            audit_id,
                            RequestResult(
                                provider_id=route.provider_id if route is not None else None,
                                model_route_id=route.route_id if route is not None else None,
                                outbound_protocol=route.protocol if route is not None else None,
                                prompt_tokens=usage_result.usage.input_tokens,
                                completion_tokens=usage_result.usage.output_tokens,
                                usage_source=usage_result.usage_source,
                                cost=cost,
                                latency_ms=_elapsed_ms(started_at),
                            ),
                        )


def get_websocket_gateway_service(
    websocket: WebSocket,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebSocketGatewayService:
    billing = getattr(websocket.app.state, "billing_service", None)
    audit = getattr(websocket.app.state, "audit_service", None)
    if not isinstance(billing, BillingService):
        raise RuntimeError("application billing service is not configured")
    if not isinstance(audit, AuditService):
        raise RuntimeError("application audit service is not configured")
    return WebSocketGatewayService(
        session=session,
        settings=settings,
        billing_service=billing,
        audit_service=audit,
    )


@router.websocket("/v1/realtime")
async def openai_realtime(
    websocket: WebSocket,
    service: Annotated[WebSocketGatewayService, Depends(get_websocket_gateway_service)],
) -> None:
    await service.handle(websocket, Protocol.OPENAI)


@router.websocket("/v1beta/live")
async def gemini_live(
    websocket: WebSocket,
    service: Annotated[WebSocketGatewayService, Depends(get_websocket_gateway_service)],
) -> None:
    await service.handle(websocket, Protocol.GEMINI)


async def _initial_request_and_model(
    websocket: WebSocket,
    protocol: Protocol,
) -> tuple[Frame | None, str]:
    query_model = websocket.query_params.get("model")
    if query_model is not None and query_model.strip():
        return None, _normalize_requested_model(query_model, protocol)
    event = await websocket.receive()
    if event.get("type") == "websocket.disconnect":
        raise _GatewayClose(4400, "invalid_request")
    frame: Frame | None = event.get("text")
    if frame is None:
        frame = event.get("bytes")
    if not isinstance(frame, (str, bytes)):
        raise _GatewayClose(4400, "invalid_request")
    model = _model_from_initial_frame(frame, protocol)
    if model is None:
        raise _GatewayClose(4400, "invalid_request")
    return frame, _normalize_requested_model(model, protocol)


def _model_from_initial_frame(frame: Frame, protocol: Protocol) -> str | None:
    try:
        payload = orjson.loads(frame)
    except (orjson.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    if protocol is Protocol.OPENAI:
        session = payload.get("session")
        if isinstance(session, Mapping) and isinstance(session.get("model"), str):
            return cast(str, session["model"])
        return payload.get("model") if isinstance(payload.get("model"), str) else None
    setup = payload.get("setup")
    if isinstance(setup, Mapping) and isinstance(setup.get("model"), str):
        return cast(str, setup["model"])
    return None


def estimate_websocket_frame_tokens(frame: Frame | None) -> int:
    if frame is None:
        return 0
    if isinstance(frame, bytes):
        try:
            text = frame.decode()
        except UnicodeDecodeError:
            return max(1, (len(frame) + 959) // 960)
    else:
        text = frame
    try:
        payload = orjson.loads(text)
    except orjson.JSONDecodeError:
        return estimate_text_tokens(text)
    metadata_tokens = _metadata_token_estimate(payload)
    if metadata_tokens == 0:
        return estimate_text_tokens(text)
    return metadata_tokens


def _metadata_token_estimate(value: Any, key: str = "") -> int:
    if isinstance(value, Mapping):
        return sum(
            _metadata_token_estimate(child, str(child_key).lower())
            for child_key, child in value.items()
        )
    if isinstance(value, list):
        return sum(_metadata_token_estimate(child, key) for child in value)
    if isinstance(value, str):
        if key in {"audio", "audio_data", "data"} and len(value) > 100:
            audio_bytes = len(value) * 3 // 4
            return max(1, (audio_bytes + 959) // 960)
        if key in {"text", "transcript", "input_text", "output_text"}:
            return estimate_text_tokens(value)
    return 0


def _native_usage(protocol: Protocol, frame: Frame) -> CanonicalUsage | None:
    try:
        payload = orjson.loads(frame)
    except (orjson.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    if protocol is Protocol.OPENAI:
        response = payload.get("response")
        usage = response.get("usage") if isinstance(response, Mapping) else payload.get("usage")
        if not isinstance(usage, Mapping):
            return None
        return _usage_from_fields(
            usage,
            ("input_tokens", "prompt_tokens"),
            ("output_tokens", "completion_tokens"),
        )
    usage = payload.get("usageMetadata") or payload.get("usage_metadata")
    server_content = payload.get("serverContent") or payload.get("server_content")
    if usage is None and isinstance(server_content, Mapping):
        usage = server_content.get("usageMetadata") or server_content.get("usage_metadata")
    if not isinstance(usage, Mapping):
        return None
    return _usage_from_fields(
        usage,
        ("promptTokenCount", "prompt_token_count", "input_tokens"),
        ("candidatesTokenCount", "candidates_token_count", "output_tokens"),
    )


def _usage_from_fields(
    usage: Mapping[str, Any],
    input_fields: tuple[str, ...],
    output_fields: tuple[str, ...],
) -> CanonicalUsage | None:
    input_value = next((usage[name] for name in input_fields if name in usage), None)
    output_value = next((usage[name] for name in output_fields if name in usage), None)
    if not isinstance(input_value, int) or isinstance(input_value, bool) or input_value < 0:
        return None
    if not isinstance(output_value, int) or isinstance(output_value, bool) or output_value < 0:
        return None
    return CanonicalUsage(input_value, output_value)


def _usage_delta(current: CanonicalUsage, settled: CanonicalUsage) -> CanonicalUsage:
    return CanonicalUsage(
        max(0, current.input_tokens - settled.input_tokens),
        max(0, current.output_tokens - settled.output_tokens),
    )


def _total_tokens(usage: CanonicalUsage) -> int:
    return usage.input_tokens + usage.output_tokens


def _normalize_requested_model(model: str, protocol: Protocol) -> str:
    normalized = model.strip()
    if protocol is Protocol.GEMINI:
        normalized = normalized.removeprefix("models/")
    if not normalized:
        raise _GatewayClose(4400, "invalid_request")
    return normalized


def _frame_bytes(frame: Frame | None) -> bytes:
    if frame is None:
        return b""
    return frame if isinstance(frame, bytes) else frame.encode()


def _gateway_close(exc: BaseException) -> _GatewayClose:
    if isinstance(exc, _GatewayClose):
        return exc
    if isinstance(exc, InsufficientBalance):
        return _GatewayClose(4402, "insufficient_balance")
    if isinstance(exc, NoRouteAvailable) and exc.removed_by_transport:
        return _GatewayClose(4400, "unsupported_transport")
    if isinstance(exc, HTTPException):
        detail = exc.detail
        code = detail.get("code") if isinstance(detail, Mapping) else None
        return _GatewayClose(4401, str(code or "invalid_api_key"))
    code = getattr(exc, "code", None)
    if code == "insufficient_balance":
        return _GatewayClose(4402, "insufficient_balance")
    if isinstance(code, str):
        return _GatewayClose(4400, code)
    return _GatewayClose(1011, "upstream_error")


def _close_reason(code: str) -> str:
    return orjson.dumps({"code": code}).decode()


async def _safe_close(websocket: WebSocket, code: int, reason: str) -> None:
    try:
        await websocket.close(code=code, reason=reason)
    except (OSError, RuntimeError):
        pass


async def _safe_health(operation: Any) -> None:
    try:
        await operation
    except Exception as exc:
        logger.warning("WebSocket route health update failed exception_type=%s", type(exc).__name__)


def _result_error_code(result: RelayResult) -> str:
    if isinstance(result.exception, RelayAbort):
        try:
            payload = orjson.loads(result.close_reason)
        except orjson.JSONDecodeError:
            return "websocket_closed"
        if isinstance(payload, Mapping) and isinstance(payload.get("code"), str):
            return cast(str, payload["code"])
    return "client_disconnected" if result.client_disconnected else "upstream_error"


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((monotonic() - started_at) * 1000))
