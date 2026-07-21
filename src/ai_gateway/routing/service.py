from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Select, and_, exists, false, literal, not_, or_, select, true, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ai_gateway.auth.api_key import ApiKeyPrincipal
from ai_gateway.catalog.schemas import ResolvedModel
from ai_gateway.core.enums import ApiKeyScope, Protocol, RouteRuntimeState
from ai_gateway.db.models import Model, ModelRoute, Provider, ProviderProtocol
from ai_gateway.routing.types import NoRouteAvailable, RouteCandidate

Clock = Callable[[], datetime]


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


class Router:
    def __init__(
        self,
        session: AsyncSession,
        *,
        rng: random.Random | None = None,
        clock: Clock = _utcnow,
    ) -> None:
        self._session = session
        self._rng = rng if rng is not None else random.Random()
        self._clock = clock

    async def select_route(
        self,
        model: ResolvedModel | int,
        principal: ApiKeyPrincipal,
        required_protocol: Protocol | str | None = None,
        *,
        requested_model: str | None = None,
    ) -> RouteCandidate:
        model_id, requested_name = _model_identity(model, requested_model)
        protocol = Protocol(required_protocol) if required_protocol is not None else None
        now = self._clock()
        rows = (
            (
                await self._session.execute(
                    _candidate_query(
                        model_id=model_id,
                        principal=principal,
                        required_protocol=protocol,
                        now=now,
                    )
                )
            )
            .mappings()
            .all()
        )

        first_row = rows[0]
        candidates = [_candidate_from_row(row) for row in rows if row["route_id"] is not None]
        removed_by_scope = bool(first_row["removed_by_scope"])
        removed_by_transport = bool(first_row["removed_by_transport"])
        removed_by_health = bool(first_row["removed_by_health"])

        while candidates:
            candidate = choose_weighted_route(candidates, self._rng)
            candidates.remove(candidate)
            if candidate.runtime_state is RouteRuntimeState.CLOSED:
                return candidate
            if await self._claim_half_open(candidate.route_id, now):
                return candidate
            removed_by_health = True

        raise NoRouteAvailable(
            requested_name,
            removed_by_scope=removed_by_scope,
            removed_by_transport=removed_by_transport,
            removed_by_health=removed_by_health,
        )

    async def _claim_half_open(self, route_id: int, now: datetime) -> bool:
        result = await self._session.execute(
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
        await self._session.commit()
        return claimed

    async def record_success(self, route_id: int) -> bool:
        from ai_gateway.routing.health import RouteHealth

        return await RouteHealth(self._session).record_success(route_id)

    async def record_failure(self, route_id: int, failure: object) -> bool:
        from ai_gateway.routing.health import RouteHealth

        return await RouteHealth(self._session).record_failure(route_id, failure)


RoutingService = Router


async def select_route(
    session: AsyncSession,
    model: ResolvedModel | int,
    principal: ApiKeyPrincipal,
    required_protocol: Protocol | str | None = None,
    *,
    rng: random.Random | None = None,
    clock: Clock = _utcnow,
    requested_model: str | None = None,
) -> RouteCandidate:
    return await Router(session, rng=rng, clock=clock).select_route(
        model,
        principal,
        required_protocol,
        requested_model=requested_model,
    )


def _model_identity(model: ResolvedModel | int, requested_model: str | None) -> tuple[int, str]:
    if isinstance(model, ResolvedModel):
        return model.model_id, model.requested_name
    return model, requested_model if requested_model is not None else str(model)


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


def _transport_condition(protocol: Any, required_protocol: Protocol | None) -> Any:
    if required_protocol is None:
        return true()
    return protocol.protocol == required_protocol


def _base_conditions(route: Any, model: Any, provider: Any, protocol: Any, model_id: int) -> Any:
    return and_(
        route.model_id == model_id,
        route.weight > 0,
        route.enabled.is_(True),
        model.enabled.is_(True),
        provider.enabled.is_(True),
        protocol.enabled.is_(True),
    )


def _route_exists(
    *,
    model_id: int,
    principal: ApiKeyPrincipal,
    required_protocol: Protocol | None,
    now: datetime,
    omitted_filter: str,
) -> Any:
    route = aliased(ModelRoute)
    model = aliased(Model)
    provider = aliased(Provider)
    protocol = aliased(ProviderProtocol)
    conditions = [_base_conditions(route, model, provider, protocol, model_id)]
    scope = _scope_condition(route, principal)
    transport = _transport_condition(protocol, required_protocol)
    health = _health_condition(route, now)
    for name, condition in (("scope", scope), ("transport", transport), ("health", health)):
        conditions.append(not_(condition) if name == omitted_filter else condition)
    return exists(
        select(literal(1))
        .select_from(route)
        .join(model, model.id == route.model_id)
        .join(provider, provider.id == route.provider_id)
        .join(protocol, protocol.id == route.provider_protocol_id)
        .where(*conditions)
    )


def _candidate_query(
    *,
    model_id: int,
    principal: ApiKeyPrincipal,
    required_protocol: Protocol | None,
    now: datetime,
) -> Select[tuple[Any, ...]]:
    eligible = (
        select(
            ModelRoute.id.label("route_id"),
            ModelRoute.model_id,
            ModelRoute.provider_id,
            ModelRoute.provider_protocol_id,
            ProviderProtocol.protocol,
            ProviderProtocol.base_url,
            ProviderProtocol.websocket_url,
            ModelRoute.upstream_model,
            ModelRoute.weight,
            ModelRoute.runtime_state,
            Provider.credential_encrypted.label("provider_credential_encrypted"),
            ProviderProtocol.extra_headers_encrypted,
        )
        .select_from(ModelRoute)
        .join(Model, Model.id == ModelRoute.model_id)
        .join(Provider, Provider.id == ModelRoute.provider_id)
        .join(ProviderProtocol, ProviderProtocol.id == ModelRoute.provider_protocol_id)
        .where(
            _base_conditions(ModelRoute, Model, Provider, ProviderProtocol, model_id),
            _scope_condition(ModelRoute, principal),
            _transport_condition(ProviderProtocol, required_protocol),
            _health_condition(ModelRoute, now),
        )
        .subquery("eligible_routes")
    )
    anchor = select(literal(1).label("anchor")).subquery("routing_anchor")
    removed_by_scope = _route_exists(
        model_id=model_id,
        principal=principal,
        required_protocol=required_protocol,
        now=now,
        omitted_filter="scope",
    )
    removed_by_transport = _route_exists(
        model_id=model_id,
        principal=principal,
        required_protocol=required_protocol,
        now=now,
        omitted_filter="transport",
    )
    removed_by_health = _route_exists(
        model_id=model_id,
        principal=principal,
        required_protocol=required_protocol,
        now=now,
        omitted_filter="health",
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
        upstream_model=cast(str, row["upstream_model"]),
        weight=cast(int, row["weight"]),
        runtime_state=RouteRuntimeState(row["runtime_state"]),
        provider_credential_encrypted=cast(bytes, row["provider_credential_encrypted"]),
        extra_headers_encrypted=cast(bytes | None, row["extra_headers_encrypted"]),
    )
