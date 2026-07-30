from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from time import monotonic
from typing import Annotated, Any, cast
from typing import Protocol as TypingProtocol
from uuid import UUID, uuid4

import anyio
import orjson
from fastapi import APIRouter, Depends, HTTPException, WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.audit.service import AuditService, RequestContext, RequestFailure, RequestResult
from ai_gateway.auth.api_key import ApiKeyPrincipal, authenticate_api_key, extract_api_key
from ai_gateway.billing.pricing import PricedModel
from ai_gateway.billing.service import (
    AdjustmentResult,
    BalanceReservation,
    BillingService,
    InsufficientBalance,
    ReservationRecovery,
    SettlementResult,
    _settlement_costs,
)
from ai_gateway.billing.usage import (
    UsageResult,
    estimate_text_tokens,
    extract_native_openai_usage,
    extract_provider_usage,
)
from ai_gateway.catalog.repository import CatalogRepository
from ai_gateway.catalog.schemas import ResolvedModel
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol, UsageSource
from ai_gateway.core.errors import GatewayError
from ai_gateway.db.models import Model, Provider
from ai_gateway.db.session import get_session
from ai_gateway.protocols.types import CanonicalUsage
from ai_gateway.routing.service import router_for_settings
from ai_gateway.routing.types import NoRouteAvailable, RouteCandidate, RouteFailure
from ai_gateway.transport.websocket import (
    Frame,
    RelayAbort,
    RelayHealthOutcome,
    RelayResult,
    UpstreamWebSocketError,
    relay_websocket,
    select_websocket_subprotocols,
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
        recovery: ReservationRecovery | None = None,
        provider: Provider | None = None,
    ) -> BalanceReservation: ...

    async def settle_request(
        self,
        *,
        reservation_id: int,
        idempotency_key: str,
        model: PricedModel | None = None,
        usage: CanonicalUsage | None = None,
        cost: Decimal | None = None,
        cost_amount: Decimal | None = None,
        usage_source: UsageSource | None = None,
        provider: Provider | None = None,
    ) -> SettlementResult: ...

    async def update_reservation_recovery(
        self,
        *,
        reservation_id: int,
        recovery: ReservationRecovery,
    ) -> bool: ...

    async def reconcile_charge(
        self,
        *,
        user_id: int,
        request_id: str,
        amount: Decimal,
        idempotency_key: str,
        reason: str = "provider_usage_reconciliation",
    ) -> AdjustmentResult: ...


class RouteSelector(TypingProtocol):
    async def select_route(
        self,
        model: ResolvedModel | int,
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
        self._native_input = 0
        self._native_output = 0
        self._native_cache_read = 0
        self._native_cache_write = 0
        self._native_estimated_input = 0
        self._native_estimated_output = 0
        self._has_native = False
        self._openai_response_ids: set[str] = set()
        self._gemini_last = CanonicalUsage(0, 0)

    def observe_client(self, frame: Frame) -> None:
        self.observe("client", frame)

    def observe_upstream(self, frame: Frame) -> None:
        self.observe("upstream", frame)

    def observe(self, direction: str, frame: Frame) -> None:
        estimated = estimate_websocket_frame_tokens(frame)
        if direction == "client":
            self._estimated_input += estimated
            return
        native = _native_usage_event(self.protocol, frame)
        if native is not None:
            if self._apply_native(native):
                self._native_estimated_input = self._estimated_input
                self._native_estimated_output = self._estimated_output
            return
        self._estimated_output += estimated

    def preview(self, direction: str, frame: Frame) -> UsageResult:
        projected = self._copy()
        projected.observe(direction, frame)
        return projected.snapshot()

    def snapshot(self) -> UsageResult:
        if self._has_native:
            estimated_tail = CanonicalUsage(
                max(0, self._estimated_input - self._native_estimated_input),
                max(0, self._estimated_output - self._native_estimated_output),
            )
            source = (
                UsageSource.ESTIMATED if _total_tokens(estimated_tail) > 0 else UsageSource.PROVIDER
            )
            return UsageResult(
                CanonicalUsage(
                    self._native_input + estimated_tail.input_tokens,
                    self._native_output + estimated_tail.output_tokens,
                    self._native_cache_read,
                    self._native_cache_write,
                ),
                source,
            )
        return UsageResult(
            CanonicalUsage(self._estimated_input, self._estimated_output),
            UsageSource.ESTIMATED,
        )

    def _apply_native(self, event: _NativeUsageEvent) -> bool:
        if event.cumulative:
            input_delta = _counter_delta(event.usage.input_tokens, self._gemini_last.input_tokens)
            output_delta = _counter_delta(
                event.usage.output_tokens,
                self._gemini_last.output_tokens,
            )
            cache_read_delta = _counter_delta(
                event.usage.cache_read_tokens,
                self._gemini_last.cache_read_tokens,
            )
            cache_write_delta = _counter_delta(
                event.usage.cache_write_tokens,
                self._gemini_last.cache_write_tokens,
            )
            if input_delta == output_delta == cache_read_delta == cache_write_delta == 0:
                return False
            self._gemini_last = event.usage
        else:
            if event.identity in self._openai_response_ids:
                return False
            self._openai_response_ids.add(event.identity)
            input_delta = event.usage.input_tokens
            output_delta = event.usage.output_tokens
            cache_read_delta = event.usage.cache_read_tokens
            cache_write_delta = event.usage.cache_write_tokens
        self._native_input += input_delta
        self._native_output += output_delta
        self._native_cache_read += cache_read_delta
        self._native_cache_write += cache_write_delta
        self._has_native = True
        return True

    def _copy(self) -> WebSocketUsage:
        copied = WebSocketUsage(self.protocol)
        copied._estimated_input = self._estimated_input
        copied._estimated_output = self._estimated_output
        copied._native_input = self._native_input
        copied._native_output = self._native_output
        copied._native_cache_read = self._native_cache_read
        copied._native_cache_write = self._native_cache_write
        copied._native_estimated_input = self._native_estimated_input
        copied._native_estimated_output = self._native_estimated_output
        copied._has_native = self._has_native
        copied._openai_response_ids = self._openai_response_ids.copy()
        copied._gemini_last = self._gemini_last
        return copied


@dataclass(frozen=True, slots=True)
class _NativeUsageEvent:
    usage: CanonicalUsage
    identity: str
    cumulative: bool


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
        reservation_ttl_seconds: float = 300,
        provider: Provider | None = None,
    ) -> None:
        self._billing = billing
        self._user_id = user_id
        self._model = model
        self._billing_key = billing_key
        self._usage = usage
        self._max_output_tokens = max_output_tokens
        self._token_threshold = token_threshold
        self._interval_seconds = interval_seconds
        self._reservation_ttl_seconds = reservation_ttl_seconds
        self._reservation: BalanceReservation | None = None
        self._settled_usage = CanonicalUsage(0, 0)
        self._sequence = 0
        self._last_checkpoint = monotonic()
        self._finalized = False
        self._reconciliation_sequence = 0
        self._last_settled_request_id: str | None = None
        self._lock = anyio.Lock()
        self._provider = provider
        self.actual_cost = Decimal("0")
        self.cost_amount = Decimal("0")
        self.charged_cost = Decimal("0")
        self.uncollected_cost = Decimal("0")

    @property
    def has_open_reservation(self) -> bool:
        return self._reservation is not None

    @property
    def incurred_cost(self) -> Decimal:
        return self._costs(self._usage.snapshot().usage)[0]

    @property
    def incurred_cost_amount(self) -> Decimal:
        return self._costs(self._usage.snapshot().usage)[1]

    @property
    def reported_uncollected_cost(self) -> Decimal:
        return max(self.uncollected_cost, self.incurred_cost - self.charged_cost)

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
            await self._update_recovery_locked(current)
            await self._checkpoint_locked(current)
            return True

    async def authorize_frame(self, direction: str, frame: Frame) -> None:
        async with self._lock:
            if self._finalized or self._reservation is None:
                raise RuntimeError("WebSocket billing authorization is not active")
            if direction == "upstream":
                self._usage.observe(direction, frame)
                await self._commit_incurred_locked()
                return
            current = self._usage.snapshot()
            projected = self._usage.preview(direction, frame)
            current_delta = _usage_delta(current.usage, self._settled_usage)
            projected_delta = _usage_delta(projected.usage, self._settled_usage)
            frame_delta = _usage_delta(projected.usage, current.usage)
            projected_cost = self._pending_cost(projected)
            elapsed = monotonic() - self._last_checkpoint
            checkpoint_due = (
                projected_cost > self._reservation.amount
                or elapsed >= self._interval_seconds
                or (
                    _total_tokens(projected_delta) >= self._token_threshold
                    and _total_tokens(current_delta) > 0
                )
            )
            if checkpoint_due:
                await self._checkpoint_locked(current, required_next=frame_delta)
            if self._reservation is None:
                raise RuntimeError("WebSocket billing reservation disappeared")
            next_cost = self._pending_cost(projected)
            if next_cost > self._reservation.amount:
                raise InsufficientBalance(
                    required=next_cost,
                    available=self._reservation.amount,
                )

    async def commit_frame(self, direction: str, frame: Frame) -> None:
        if direction != "client":
            return
        async with self._lock:
            if self._finalized or self._reservation is None:
                raise RuntimeError("WebSocket billing commit is not active")
            self._usage.observe(direction, frame)
            await self._commit_incurred_locked()

    async def _commit_incurred_locked(self) -> None:
        current = self._usage.snapshot()
        await self._update_recovery_locked(current)
        if await self._reconcile_locked(current):
            return
        current_delta = _usage_delta(current.usage, self._settled_usage)
        elapsed = monotonic() - self._last_checkpoint
        if self._reservation is None:
            raise RuntimeError("WebSocket billing reservation disappeared")
        if (
            self._pending_cost(current) > self._reservation.amount
            or elapsed >= self._interval_seconds
            or _total_tokens(current_delta) >= self._token_threshold
        ):
            await self._checkpoint_locked(current)

    async def finalize(self) -> None:
        for attempt in range(3):
            try:
                async with self._lock:
                    if self._finalized:
                        return
                    if self._reservation is not None:
                        await self._update_recovery_locked(self._usage.snapshot())
                        await self._checkpoint_locked(self._usage.snapshot(), final=True)
                    self._finalized = True
                return
            except Exception:
                if attempt == 2:
                    raise
                await anyio.sleep(0)

    async def _reserve(
        self,
        estimated_input_tokens: int,
        *,
        max_output_tokens: int | None = None,
    ) -> BalanceReservation:
        sequence = self._sequence
        self._sequence += 1
        return await self._billing.reserve_balance(
            user_id=self._user_id,
            model=self._model,
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=(
                self._max_output_tokens if max_output_tokens is None else max_output_tokens
            ),
            idempotency_key=f"{self._billing_key}:reserve:{sequence}",
            request_id=uuid4(),
            recovery=self._recovery(CanonicalUsage(0, 0), UsageSource.ESTIMATED, sequence),
            provider=self._provider,
        )

    async def _checkpoint_locked(
        self,
        current: UsageResult,
        *,
        required_next: CanonicalUsage | None = None,
        final: bool = False,
    ) -> None:
        if self._reservation is None:
            return
        if await self._reconcile_locked(current):
            if final:
                current = self._usage.snapshot()
            else:
                return
        usage_delta = _usage_delta(current.usage, self._settled_usage)
        target_cost, target_cost_amount = self._costs(current.usage)
        monetary_delta = max(Decimal("0"), target_cost - self.charged_cost)
        cost_amount_delta = max(Decimal("0"), target_cost_amount - self.cost_amount)
        settled_reservation = self._reservation
        if settled_reservation is None:
            return
        settlement = await self._settle(
            settled_reservation,
            usage_delta,
            current.usage_source,
            monetary_delta,
            cost_amount_delta,
        )
        self._reservation = None
        self.actual_cost = target_cost
        self.cost_amount = target_cost_amount
        self.charged_cost += settlement.charged_amount
        self.uncollected_cost = max(Decimal("0"), target_cost - self.charged_cost)
        self._last_settled_request_id = settled_reservation.request_id
        self._settled_usage = current.usage
        self._last_checkpoint = monotonic()
        if settlement.exhausted and not final:
            raise InsufficientBalance(required=Decimal("0.00000001"), available=Decimal("0"))
        if not final:
            required = required_next or CanonicalUsage(0, 0)
            self._reservation = await self._reserve(
                required.input_tokens,
                max_output_tokens=max(self._max_output_tokens, required.output_tokens),
            )
            await self._update_recovery_locked(current)

    async def _reconcile_locked(self, current: UsageResult) -> bool:
        target_cost, target_cost_amount = self._costs(current.usage)
        if target_cost >= self.charged_cost:
            return False
        refund = self.charged_cost - target_cost
        request_id = self._last_settled_request_id
        if request_id is None:
            return False
        if refund > 0:
            sequence = self._reconciliation_sequence
            await self._billing.reconcile_charge(
                user_id=self._user_id,
                request_id=request_id,
                amount=refund,
                idempotency_key=f"{self._billing_key}:reconcile:{sequence}",
            )
            self._reconciliation_sequence += 1
        self.actual_cost = target_cost
        self.cost_amount = target_cost_amount
        self.charged_cost = target_cost
        self.uncollected_cost = Decimal("0")
        self._settled_usage = current.usage
        await self._update_recovery_locked(current)
        return True

    async def _update_recovery_locked(self, current: UsageResult) -> None:
        if self._reservation is None:
            return
        delta = _usage_delta(current.usage, self._settled_usage)
        await self._billing.update_reservation_recovery(
            reservation_id=self._reservation.ledger_entry_id,
            recovery=self._recovery(
                delta,
                current.usage_source,
                self._sequence - 1,
                cost=self._pending_cost(current),
                cost_amount=self._pending_cost_amount(current),
            ),
        )

    def _recovery(
        self,
        usage: CanonicalUsage,
        usage_source: UsageSource,
        sequence: int,
        *,
        cost: Decimal = Decimal("0"),
        cost_amount: Decimal = Decimal("0"),
    ) -> ReservationRecovery:
        return ReservationRecovery(
            settlement_key=f"{self._billing_key}:settle:{sequence}",
            usage=usage,
            usage_source=usage_source,
            expires_at=datetime.now(UTC).replace(tzinfo=None)
            + timedelta(seconds=self._reservation_ttl_seconds),
            cost=cost,
            cost_amount=cost_amount,
        )

    def _pending_cost(self, current: UsageResult) -> Decimal:
        return max(Decimal("0"), self._costs(current.usage)[0] - self.charged_cost)

    def _pending_cost_amount(self, current: UsageResult) -> Decimal:
        return max(Decimal("0"), self._costs(current.usage)[1] - self.cost_amount)

    def _costs(self, usage: CanonicalUsage) -> tuple[Decimal, Decimal]:
        return _settlement_costs(
            model=self._model,
            usage=usage,
            cost=None,
            cost_amount=None,
            provider=self._provider,
        )

    async def _settle(
        self,
        reservation: BalanceReservation,
        usage: CanonicalUsage,
        usage_source: UsageSource,
        cost: Decimal,
        cost_amount: Decimal,
    ) -> SettlementResult:
        return await self._billing.settle_request(
            reservation_id=reservation.ledger_entry_id,
            idempotency_key=f"{self._billing_key}:settle:{self._sequence - 1}",
            usage=usage,
            cost=cost,
            cost_amount=cost_amount,
            usage_source=usage_source,
            provider=self._provider,
        )


class WebSocketGatewayService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        billing_service: BillingBackend,
        audit_service: AuditService,
        router_factory: Callable[[AsyncSession], RouteSelector] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._billing = billing_service
        self._audit = audit_service
        if router_factory is None:
            self._router_factory: Callable[[AsyncSession], RouteSelector] = lambda active_session: (
                router_for_settings(active_session, settings)
            )
        else:
            self._router_factory = router_factory

    async def handle(self, websocket: WebSocket, protocol: Protocol) -> None:
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
        except BaseException as exc:
            if isinstance(exc, anyio.get_cancelled_exc_class()):
                raise
            close = _gateway_close(exc)
            await _reject_websocket(websocket, close.code, _close_reason(close.error_code))
            return

        raw_subprotocols = websocket.headers.get("sec-websocket-protocol")
        upstream_subprotocols, selected_subprotocol = select_websocket_subprotocols(
            protocol,
            raw_subprotocols,
        )
        await websocket.accept(subprotocol=selected_subprotocol)
        try:
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
            if isinstance(self._session, AsyncSession):
                priced_model = await self._session.scalar(
                    select(Model)
                    .where(Model.id == resolved.model_id)
                    .options(selectinload(Model.price_tiers))
                )
            else:
                priced_model = await self._session.get(Model, resolved.model_id)
            if priced_model is None:
                raise RuntimeError("resolved catalog model disappeared")

            # Load provider for billing multiplier application
            provider = await self._session.get(Provider, route.provider_id)

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
                reservation_ttl_seconds=getattr(
                    self._settings,
                    "billing_reservation_ttl_seconds",
                    300,
                ),
                provider=provider,
            )
            await billing_cycle.reserve_initial(
                estimated_input_tokens=estimate_websocket_frame_tokens(initial_request)
            )

            async def observe(direction: str, frame: Frame) -> None:
                try:
                    await billing_cycle.authorize_frame(direction, frame)
                except InsufficientBalance:
                    raise RelayAbort(4402, _close_reason("insufficient_balance")) from None

            async def commit(direction: str, frame: Frame) -> None:
                try:
                    await billing_cycle.commit_frame(direction, frame)
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
                commit_frame=commit,
                on_interval=interval,
                subprotocols=upstream_subprotocols,
            )
            if result.health_outcome is RelayHealthOutcome.FAILURE:
                await _safe_health(
                    route_router.record_failure(
                        route.route_id,
                        result.route_failure
                        or RouteFailure(
                            error_code="websocket_network_error",
                            exception=result.exception,
                        ),
                    )
                )
            elif result.health_outcome is RelayHealthOutcome.SUCCESS:
                await _safe_health(route_router.record_success(route.route_id))
        except BaseException as exc:
            if isinstance(exc, anyio.get_cancelled_exc_class()):
                result = RelayResult(
                    client_disconnected=True,
                    close_code=1001,
                    close_reason="client disconnected",
                    exception=exc,
                    health_outcome=RelayHealthOutcome.NEUTRAL,
                )
                raise
            if (
                route is not None
                and route_router is not None
                and isinstance(exc, UpstreamWebSocketError)
            ):
                await _safe_health(route_router.record_failure(route.route_id, exc.failure))
            close = _gateway_close(exc)
            await _safe_close(websocket, close.code, _close_reason(close.error_code))
            result = RelayResult(
                client_disconnected=False,
                upstream_failed=isinstance(exc, UpstreamWebSocketError),
                close_code=close.code,
                close_reason=_close_reason(close.error_code),
                exception=exc,
                health_outcome=(
                    RelayHealthOutcome.FAILURE
                    if isinstance(exc, UpstreamWebSocketError)
                    else RelayHealthOutcome.NEUTRAL
                ),
                route_failure=exc.failure if isinstance(exc, UpstreamWebSocketError) else None,
            )
        finally:
            cleanup_error: BaseException | None = None
            with anyio.CancelScope(shield=True):
                if billing_cycle is not None:
                    try:
                        await billing_cycle.finalize()
                    except Exception as exc:
                        cleanup_error = exc
                        logger.error(
                            "WebSocket billing cleanup failed exception_type=%s",
                            type(exc).__name__,
                        )
            if cleanup_error is not None:
                result = RelayResult(
                    client_disconnected=(
                        result.client_disconnected if result is not None else False
                    ),
                    close_code=1011,
                    close_reason="billing cleanup failed",
                    exception=cleanup_error,
                    health_outcome=RelayHealthOutcome.NEUTRAL,
                )
            with anyio.CancelScope(shield=True):
                if audit_id is not None:
                    usage_result = usage.snapshot()
                    cost = (
                        billing_cycle.incurred_cost if billing_cycle is not None else Decimal("0")
                    )
                    cost_amount = (
                        billing_cycle.incurred_cost_amount
                        if billing_cycle is not None
                        else Decimal("0")
                    )
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
                                cache_read_tokens=usage_result.usage.cache_read_tokens,
                                cache_write_tokens=usage_result.usage.cache_write_tokens,
                                usage_source=usage_result.usage_source,
                                cost=cost,
                                cost_amount=cost_amount,
                                latency_ms=_elapsed_ms(started_at),
                                metadata=_billing_audit_metadata(billing_cycle),
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
                                cache_read_tokens=usage_result.usage.cache_read_tokens,
                                cache_write_tokens=usage_result.usage.cache_write_tokens,
                                usage_source=usage_result.usage_source,
                                cost=cost,
                                cost_amount=cost_amount,
                                latency_ms=_elapsed_ms(started_at),
                                metadata=_billing_audit_metadata(billing_cycle),
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


def _native_usage_event(protocol: Protocol, frame: Frame) -> _NativeUsageEvent | None:
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
        operation = "responses" if "input_tokens" in usage else "chat_completions"
        try:
            parsed = extract_native_openai_usage(operation, {"usage": usage})
        except (GatewayError, ValueError):
            parsed = None
        if parsed is None:
            return None
        response_id = response.get("id") if isinstance(response, Mapping) else None
        if not isinstance(response_id, str) or not response_id:
            raw_id = payload.get("response_id")
            response_id = raw_id if isinstance(raw_id, str) and raw_id else _frame_digest(frame)
        return _NativeUsageEvent(parsed, response_id, False)
    usage = payload.get("usageMetadata") or payload.get("usage_metadata")
    server_content = payload.get("serverContent") or payload.get("server_content")
    if usage is None and isinstance(server_content, Mapping):
        usage = server_content.get("usageMetadata") or server_content.get("usage_metadata")
    if not isinstance(usage, Mapping):
        return None
    try:
        parsed = extract_provider_usage(Protocol.GEMINI, {"usageMetadata": usage})
    except (GatewayError, ValueError):
        parsed = None
    if parsed is None:
        return None
    return _NativeUsageEvent(parsed, _frame_digest(frame), True)


def _usage_delta(current: CanonicalUsage, settled: CanonicalUsage) -> CanonicalUsage:
    return CanonicalUsage(
        max(0, current.input_tokens - settled.input_tokens),
        max(0, current.output_tokens - settled.output_tokens),
        max(0, current.cache_read_tokens - settled.cache_read_tokens),
        max(0, current.cache_write_tokens - settled.cache_write_tokens),
    )


def _counter_delta(current: int, previous: int) -> int:
    return current - previous if current >= previous else current


def _frame_digest(frame: Frame) -> str:
    raw = frame if isinstance(frame, bytes) else frame.encode()
    return sha256(raw).hexdigest()


def _total_tokens(usage: CanonicalUsage) -> int:
    return (
        usage.input_tokens
        + usage.output_tokens
        + usage.cache_read_tokens
        + usage.cache_write_tokens
    )


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


async def _reject_websocket(websocket: WebSocket, code: int, reason: str) -> None:
    try:
        await websocket.accept()
    except (OSError, RuntimeError):
        pass
    await _safe_close(websocket, code, reason)


async def _safe_health(operation: Any) -> None:
    try:
        await operation
    except Exception as exc:
        logger.warning("WebSocket route health update failed exception_type=%s", type(exc).__name__)


def _result_error_code(result: RelayResult) -> str:
    if result.close_reason == "billing cleanup failed":
        return "billing_cleanup_failed"
    if isinstance(result.exception, RelayAbort):
        try:
            payload = orjson.loads(result.close_reason)
        except orjson.JSONDecodeError:
            return "websocket_closed"
        if isinstance(payload, Mapping) and isinstance(payload.get("code"), str):
            return cast(str, payload["code"])
    if result.internal_failed:
        return "internal_error"
    return "client_disconnected" if result.client_disconnected else "upstream_error"


def _billing_audit_metadata(cycle: WebSocketBillingCycle | None) -> dict[str, str]:
    if cycle is None:
        return {}
    return {
        "charged_cost": str(cycle.charged_cost),
        "uncollected_cost": str(cycle.reported_uncollected_cost),
        "billing_recovery_pending": str(cycle.has_open_reservation).lower(),
    }


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((monotonic() - started_at) * 1000))
