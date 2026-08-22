from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import Select, and_, exists, false, literal, not_, or_, select, true, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ai_gateway.auth.api_key import ApiKeyPrincipal
from ai_gateway.catalog.schemas import ResolvedModel
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import ApiKeyScope, Protocol, RouteRuntimeState
from ai_gateway.db.models import Model, ModelRoute, Provider, ProviderProtocol
from ai_gateway.routing.sessions import MutationSessionFactory, mutation_session_factory_for
from ai_gateway.routing.types import NoRouteAvailable, RouteCandidate

Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)
_PROTOCOL_FALLBACK_ORDER = {
    Protocol.OPENAI: 0,
    Protocol.CLAUDE: 1,
    Protocol.GEMINI: 2,
}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def choose_weighted_route(
    candidates: Sequence[RouteCandidate],
    rng: random.Random,
) -> RouteCandidate:
    if not candidates:
        raise ValueError("at least one route candidate is required")
    total_weight = sum(candidate.weight for candidate in candidates)
    if total_weight <= 0:
        raise ValueError("route candidate weights must have a positive sum")

    ticket = rng.uniform(0, total_weight)
    cumulative_weight = 0
    for candidate in candidates:
        cumulative_weight += candidate.weight
        if ticket <= cumulative_weight:
            return candidate
    return candidates[-1]


def lowest_cost_candidates(candidates: Sequence[RouteCandidate]) -> list[RouteCandidate]:
    if not candidates:
        return []
    lowest_cost = min(candidate.provider_cost_multiplier for candidate in candidates)
    return [
        candidate for candidate in candidates if candidate.provider_cost_multiplier == lowest_cost
    ]


class Router:
    def __init__(
        self,
        session: AsyncSession,
        *,
        rng: random.Random | None = None,
        clock: Clock = _utcnow,
        mutation_session_factory: MutationSessionFactory | None = None,
        failure_threshold: int = 10,
        cooldown: timedelta = timedelta(seconds=60),
    ) -> None:
        self._session = session
        self._rng = rng if rng is not None else random.Random()
        self._clock = clock
        self._mutation_session_factory = (
            mutation_session_factory
            if mutation_session_factory is not None
            else mutation_session_factory_for(session)
        )
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown

    async def select_route(
        self,
        model: ResolvedModel | int,
        principal: ApiKeyPrincipal,
        required_protocol: Protocol | str | None = None,
        *,
        preferred_protocol: Protocol | str | None = None,
        requested_model: str | None = None,
        excluded_route_ids: frozenset[int] | set[int] = frozenset(),
        require_websocket: bool = False,
        preferred_provider_id: int | None = None,
    ) -> RouteCandidate:
        model_ids, requested_name = _model_identity(model, requested_model)
        protocol = Protocol(required_protocol) if required_protocol is not None else None
        preferred = Protocol(preferred_protocol) if preferred_protocol is not None else protocol
        now = self._clock()
        with self._session.no_autoflush:
            rows = (
                (
                    await self._session.execute(
                        _candidate_query(
                            model_ids=model_ids,
                            principal=principal,
                            required_protocol=protocol,
                            require_websocket=require_websocket,
                            now=now,
                            excluded_route_ids=excluded_route_ids,
                        )
                    )
                )
                .mappings()
                .all()
            )

        first_row = rows[0]
        candidates = _candidates_from_rows(rows, preferred)
        removed_by_scope = bool(first_row["removed_by_scope"])
        removed_by_transport = bool(first_row["removed_by_transport"])
        removed_by_health = bool(first_row["removed_by_health"])

        affinity_candidates = [
            candidate
            for candidate in candidates
            if preferred_provider_id is not None and candidate.provider_id == preferred_provider_id
        ]
        remaining_candidates = [
            candidate for candidate in candidates if candidate not in affinity_candidates
        ]
        preferred_candidates = (
            [candidate for candidate in remaining_candidates if candidate.protocol is preferred]
            if preferred is not None
            else []
        )
        fallback_candidates = (
            [candidate for candidate in remaining_candidates if candidate.protocol is not preferred]
            if preferred_candidates
            else remaining_candidates
        )
        protocol_pools = (
            [preferred_candidates, fallback_candidates]
            if preferred_candidates
            else [remaining_candidates]
        )
        pools = ([affinity_candidates] if affinity_candidates else []) + protocol_pools
        for pool in pools:
            while pool:
                cost_tier = lowest_cost_candidates(pool)
                for candidate in cost_tier:
                    pool.remove(candidate)
                while cost_tier:
                    candidate = choose_weighted_route(cost_tier, self._rng)
                    cost_tier.remove(candidate)
                    if candidate.runtime_state is RouteRuntimeState.CLOSED:
                        return candidate
                    if await self._claim_half_open_cancellation_safe(candidate.route_id, now):
                        return replace(
                            candidate,
                            runtime_state=RouteRuntimeState.HALF_OPEN,
                            disabled_until=None,
                        )
                    removed_by_health = True

        raise NoRouteAvailable(
            requested_name,
            removed_by_scope=removed_by_scope,
            removed_by_transport=removed_by_transport,
            removed_by_health=removed_by_health,
        )

    async def _claim_half_open_cancellation_safe(
        self,
        route_id: int,
        now: datetime,
    ) -> bool:
        claim_task = asyncio.create_task(self._claim_half_open(route_id, now))
        try:
            return await asyncio.shield(claim_task)
        except asyncio.CancelledError as cancellation:
            try:
                claimed = await _await_bool_task_shielded(claim_task)
            except BaseException as exc:
                logger.error(
                    "Half-open claim completion failed route_id=%s exception_type=%s",
                    route_id,
                    type(exc).__name__,
                )
                raise cancellation from None
            if claimed:
                release_task = asyncio.create_task(self.release_half_open(route_id))
                try:
                    await _await_bool_task_shielded(release_task)
                except BaseException as exc:
                    logger.error(
                        "Half-open claim release failed route_id=%s exception_type=%s",
                        route_id,
                        type(exc).__name__,
                    )
            raise

    async def has_eligible_route(
        self,
        model: ResolvedModel | int,
        principal: ApiKeyPrincipal,
        required_protocol: Protocol | str | None = None,
    ) -> bool:
        model_ids, _ = _model_identity(model, None)
        protocol = Protocol(required_protocol) if required_protocol is not None else None
        rows = (
            (
                await self._session.execute(
                    _candidate_query(
                        model_ids=model_ids,
                        principal=principal,
                        required_protocol=protocol,
                        require_websocket=False,
                        now=self._clock(),
                    )
                )
            )
            .mappings()
            .all()
        )
        return bool(_candidates_from_rows(rows, protocol))

    async def maximum_eligible_public_multiplier(
        self,
        model_id: int,
        principal: ApiKeyPrincipal,
        required_protocol: Protocol | str | None = None,
        *,
        require_websocket: bool = False,
    ) -> Decimal | None:
        """Return the highest public multiplier among currently eligible routes."""

        protocol = Protocol(required_protocol) if required_protocol is not None else None
        rows = (
            (
                await self._session.execute(
                    _candidate_query(
                        model_ids=(model_id,),
                        principal=principal,
                        required_protocol=protocol,
                        require_websocket=require_websocket,
                        now=self._clock(),
                    )
                )
            )
            .mappings()
            .all()
        )
        multipliers = [
            Decimal(str(row["provider_public_multiplier"]))
            for row in rows
            if row["route_id"] is not None
        ]
        return max(multipliers) if multipliers else None

    async def _claim_half_open(self, route_id: int, now: datetime) -> bool:
        async with self._mutation_session_factory() as mutation_session:
            async with mutation_session.begin():
                result = await mutation_session.execute(
                    update(ModelRoute)
                    .where(
                        ModelRoute.id == route_id,
                        ModelRoute.runtime_state == RouteRuntimeState.OPEN,
                        ModelRoute.disabled_until.is_not(None),
                        ModelRoute.disabled_until <= now,
                    )
                    .values(runtime_state=RouteRuntimeState.HALF_OPEN, disabled_until=None)
                )
                claimed = cast(CursorResult[Any], result).rowcount == 1
        return claimed

    async def release_half_open(self, route_id: int) -> bool:
        """Release an unstarted probe without recording a provider outcome."""

        async with self._mutation_session_factory() as mutation_session:
            async with mutation_session.begin():
                result = await mutation_session.execute(
                    update(ModelRoute)
                    .where(
                        ModelRoute.id == route_id,
                        ModelRoute.runtime_state == RouteRuntimeState.HALF_OPEN,
                    )
                    .values(
                        runtime_state=RouteRuntimeState.OPEN,
                        disabled_until=self._clock() - timedelta(seconds=1),
                    )
                )
                released = cast(CursorResult[Any], result).rowcount == 1
        return released

    async def record_success(self, route_id: int) -> bool:
        from ai_gateway.routing.health import RouteHealth

        return await RouteHealth(
            self._session,
            failure_threshold=self._failure_threshold,
            cooldown=self._cooldown,
            mutation_session_factory=self._mutation_session_factory,
        ).record_success(route_id)

    async def record_failure(self, route_id: int, failure: object) -> bool:
        from ai_gateway.routing.health import RouteHealth

        return await RouteHealth(
            self._session,
            failure_threshold=self._failure_threshold,
            cooldown=self._cooldown,
            mutation_session_factory=self._mutation_session_factory,
        ).record_failure(route_id, failure)


RoutingService = Router


async def _await_bool_task_shielded(task: asyncio.Task[bool]) -> bool:
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result()


def router_for_settings(session: AsyncSession, settings: Settings) -> Router:
    return Router(
        session,
        failure_threshold=settings.route_failure_threshold,
        cooldown=timedelta(seconds=settings.route_cooldown_seconds),
    )


async def select_route(
    session: AsyncSession,
    model: ResolvedModel | int,
    principal: ApiKeyPrincipal,
    required_protocol: Protocol | str | None = None,
    *,
    preferred_protocol: Protocol | str | None = None,
    rng: random.Random | None = None,
    clock: Clock = _utcnow,
    requested_model: str | None = None,
    mutation_session_factory: MutationSessionFactory | None = None,
    excluded_route_ids: frozenset[int] | set[int] = frozenset(),
    require_websocket: bool = False,
    preferred_provider_id: int | None = None,
) -> RouteCandidate:
    return await Router(
        session,
        rng=rng,
        clock=clock,
        mutation_session_factory=mutation_session_factory,
    ).select_route(
        model,
        principal,
        required_protocol,
        preferred_protocol=preferred_protocol,
        requested_model=requested_model,
        excluded_route_ids=excluded_route_ids,
        require_websocket=require_websocket,
        preferred_provider_id=preferred_provider_id,
    )


def _model_identity(
    model: ResolvedModel | int,
    requested_model: str | None,
) -> tuple[tuple[int, ...], str]:
    if isinstance(model, ResolvedModel):
        return model.model_ids, model.requested_name
    return (model,), requested_model if requested_model is not None else str(model)


def _scope_condition(
    route: Any,
    principal: ApiKeyPrincipal,
) -> Any:
    if principal.scope is ApiKeyScope.ALL:
        return true()
    provider_allowed = (
        route.provider_id.in_(principal.provider_ids) if principal.provider_ids else false()
    )
    model_allowed = route.model_id.in_(principal.model_ids) if principal.model_ids else false()
    if principal.scope is ApiKeyScope.PROVIDERS:
        return provider_allowed
    if principal.scope is ApiKeyScope.MODELS:
        return model_allowed
    return and_(provider_allowed, model_allowed)


def _health_condition(route: Any, now: datetime) -> Any:
    cooldown_elapsed = and_(route.disabled_until.is_not(None), route.disabled_until <= now)
    return or_(
        and_(
            route.runtime_state == RouteRuntimeState.CLOSED,
            or_(route.disabled_until.is_(None), route.disabled_until <= now),
        ),
        and_(route.runtime_state == RouteRuntimeState.OPEN, cooldown_elapsed),
    )


def _transport_condition(
    protocol: Any,
    required_protocol: Protocol | None,
    require_websocket: bool,
) -> Any:
    conditions = []
    if required_protocol is not None:
        conditions.append(protocol.protocol == required_protocol)
    if require_websocket:
        conditions.append(protocol.websocket_url.is_not(None))
    return and_(*conditions) if conditions else true()


def _base_conditions(
    route: Any,
    model: Any,
    provider: Any,
    protocol: Any,
    model_ids: tuple[int, ...],
) -> Any:
    return and_(
        route.model_id.in_(model_ids),
        route.weight > 0,
        route.enabled.is_(True),
        model.enabled.is_(True),
        provider.enabled.is_(True),
        protocol.enabled.is_(True),
    )


def _route_exists(
    *,
    model_ids: tuple[int, ...],
    principal: ApiKeyPrincipal,
    required_protocol: Protocol | None,
    require_websocket: bool,
    now: datetime,
    removed_filter: str,
) -> Any:
    route = aliased(ModelRoute)
    model = aliased(Model)
    provider = aliased(Provider)
    protocol = aliased(ProviderProtocol)
    filters = {
        "scope": _scope_condition(route, principal),
        "transport": _transport_condition(protocol, required_protocol, require_websocket),
        "health": _health_condition(route, now),
    }
    conditions = [
        _base_conditions(route, model, provider, protocol, model_ids),
        not_(filters[removed_filter]),
    ]
    return exists(
        select(literal(1))
        .select_from(route)
        .join(model, model.id == route.model_id)
        .join(provider, provider.id == route.provider_id)
        .join(protocol, protocol.provider_id == route.provider_id)
        .where(*conditions)
    )


def _candidate_query(
    *,
    model_ids: tuple[int, ...],
    principal: ApiKeyPrincipal,
    required_protocol: Protocol | None,
    require_websocket: bool,
    now: datetime,
    excluded_route_ids: frozenset[int] | set[int] = frozenset(),
) -> Select[tuple[Any, ...]]:
    eligible = (
        select(
            ModelRoute.id.label("route_id"),
            ModelRoute.model_id,
            ModelRoute.provider_id,
            ProviderProtocol.id.label("provider_protocol_id"),
            ProviderProtocol.protocol,
            ProviderProtocol.base_url,
            ProviderProtocol.websocket_url,
            ProviderProtocol.supports_responses,
            ModelRoute.upstream_model,
            ModelRoute.weight,
            ModelRoute.runtime_state,
            ModelRoute.disabled_until,
            Provider.credential_encrypted.label("provider_credential_encrypted"),
            Provider.proxy_config_encrypted.label("provider_proxy_config_encrypted"),
            Provider.cost_multiplier.label("provider_cost_multiplier"),
            Provider.public_multiplier.label("provider_public_multiplier"),
            ProviderProtocol.extra_headers_encrypted,
        )
        .select_from(ModelRoute)
        .join(Model, Model.id == ModelRoute.model_id)
        .join(Provider, Provider.id == ModelRoute.provider_id)
        .join(ProviderProtocol, ProviderProtocol.provider_id == ModelRoute.provider_id)
        .where(
            _base_conditions(ModelRoute, Model, Provider, ProviderProtocol, model_ids),
            _scope_condition(ModelRoute, principal),
            _transport_condition(ProviderProtocol, required_protocol, require_websocket),
            _health_condition(ModelRoute, now),
            ModelRoute.id.not_in(excluded_route_ids) if excluded_route_ids else true(),
        )
        .subquery("eligible_routes")
    )
    anchor = select(literal(1).label("anchor")).subquery("routing_anchor")
    removed_by_scope = _route_exists(
        model_ids=model_ids,
        principal=principal,
        required_protocol=required_protocol,
        require_websocket=require_websocket,
        now=now,
        removed_filter="scope",
    )
    removed_by_transport = _route_exists(
        model_ids=model_ids,
        principal=principal,
        required_protocol=required_protocol,
        require_websocket=require_websocket,
        now=now,
        removed_filter="transport",
    )
    removed_by_health = _route_exists(
        model_ids=model_ids,
        principal=principal,
        required_protocol=required_protocol,
        require_websocket=require_websocket,
        now=now,
        removed_filter="health",
    )
    return (
        select(
            *eligible.c,
            removed_by_scope.label("removed_by_scope"),
            removed_by_transport.label("removed_by_transport"),
            removed_by_health.label("removed_by_health"),
        )
        .select_from(anchor.outerjoin(eligible, true()))
        .order_by(eligible.c.route_id)
    )


def _candidate_from_row(row: Any) -> RouteCandidate:
    return RouteCandidate(
        route_id=cast(int, row["route_id"]),
        model_id=cast(int, row["model_id"]),
        provider_id=cast(int, row["provider_id"]),
        provider_protocol_id=cast(int, row["provider_protocol_id"]),
        protocol=Protocol(row["protocol"]),
        base_url=cast(str, row["base_url"]),
        websocket_url=cast(str | None, row["websocket_url"]),
        supports_responses=bool(row["supports_responses"]),
        upstream_model=cast(str, row["upstream_model"]),
        weight=cast(int, row["weight"]),
        provider_public_multiplier=Decimal(str(row["provider_public_multiplier"])),
        provider_cost_multiplier=Decimal(str(row["provider_cost_multiplier"])),
        runtime_state=RouteRuntimeState(row["runtime_state"]),
        disabled_until=cast(datetime | None, row["disabled_until"]),
        provider_credential_encrypted=cast(bytes, row["provider_credential_encrypted"]),
        proxy_config_encrypted=cast(bytes | None, row["provider_proxy_config_encrypted"]),
        extra_headers_encrypted=cast(bytes | None, row["extra_headers_encrypted"]),
    )


def _candidates_from_rows(
    rows: Sequence[Any],
    preferred_protocol: Protocol | None,
) -> list[RouteCandidate]:
    rows_by_route: dict[int, list[Any]] = {}
    for row in rows:
        route_id = row["route_id"]
        if route_id is not None:
            rows_by_route.setdefault(cast(int, route_id), []).append(row)
    candidates: list[RouteCandidate] = []
    for route_rows in rows_by_route.values():
        selected = min(
            route_rows,
            key=lambda row: (
                *_protocol_preference(Protocol(row["protocol"]), preferred_protocol),
                cast(int, row["provider_protocol_id"]),
            ),
        )
        candidates.append(_candidate_from_row(selected))
    return candidates


def _protocol_preference(
    protocol: Protocol,
    preferred_protocol: Protocol | None,
) -> tuple[int, int]:
    return (
        0 if protocol is preferred_protocol else 1,
        _PROTOCOL_FALLBACK_ORDER[protocol],
    )
