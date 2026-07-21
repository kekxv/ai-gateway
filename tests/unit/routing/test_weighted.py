from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.api_key import ApiKeyPrincipal
from ai_gateway.catalog.schemas import ResolvedModel
from ai_gateway.core.enums import ApiKeyScope, Protocol, RouteRuntimeState
from ai_gateway.db.models import Model, ModelRoute, Provider, ProviderProtocol
from ai_gateway.routing.service import Router, choose_weighted_route
from ai_gateway.routing.types import NoRouteAvailable, RouteCandidate


def candidate(route_id: int, weight: int) -> RouteCandidate:
    return RouteCandidate(
        route_id=route_id,
        model_id=10,
        provider_id=20 + route_id,
        provider_protocol_id=30 + route_id,
        protocol=Protocol.OPENAI,
        base_url="https://upstream.invalid/v1",
        websocket_url=None,
        upstream_model=f"upstream-{route_id}",
        weight=weight,
    )


def principal(
    scope: ApiKeyScope = ApiKeyScope.ALL,
    *,
    provider_ids: frozenset[int] = frozenset(),
    model_ids: frozenset[int] = frozenset(),
) -> ApiKeyPrincipal:
    return ApiKeyPrincipal(
        api_key_id=1,
        user_id=2,
        scope=scope,
        provider_ids=provider_ids,
        model_ids=model_ids,
    )


def test_weighted_choice_is_seeded_and_proportional() -> None:
    routes = [candidate(1, 1), candidate(2, 3)]
    rng = random.Random(20260721)

    second_route_count = sum(
        choose_weighted_route(routes, rng).route_id == 2 for _ in range(40_000)
    )

    assert 0.73 <= second_route_count / 40_000 <= 0.77


async def _add_route(
    session: AsyncSession,
    *,
    suffix: str,
    model_enabled: bool = True,
    provider_enabled: bool = True,
    protocol_enabled: bool = True,
    route_enabled: bool = True,
    protocol: Protocol = Protocol.OPENAI,
    runtime_state: RouteRuntimeState = RouteRuntimeState.CLOSED,
    disabled_until: datetime | None = None,
) -> tuple[ResolvedModel, ModelRoute]:
    model = Model(
        canonical_name=f"model-{suffix}",
        display_name=f"Model {suffix}",
        enabled=model_enabled,
    )
    provider = Provider(
        name=f"provider-{suffix}",
        credential_encrypted=b"secret",
        enabled=provider_enabled,
    )
    provider_protocol = ProviderProtocol(
        provider=provider,
        protocol=protocol,
        base_url=f"https://{suffix}.provider.invalid/v1",
        enabled=protocol_enabled,
    )
    route = ModelRoute(
        model=model,
        provider=provider,
        provider_protocol=provider_protocol,
        upstream_model=f"upstream-{suffix}",
        weight=100,
        enabled=route_enabled,
        runtime_state=runtime_state,
        disabled_until=disabled_until,
    )
    session.add(route)
    await session.flush()
    return (
        ResolvedModel(
            model_id=model.id,
            requested_name=f"requested-{suffix}",
            canonical_name=model.canonical_name,
        ),
        route,
    )


async def test_select_route_uses_one_unlocked_query_for_eligible_route(
    session: AsyncSession,
) -> None:
    model, route = await _add_route(session, suffix="single-query")
    statements: list[str] = []

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    sync_engine = session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", capture_statement)
    try:
        selected = await Router(session, rng=random.Random(7)).select_route(model, principal())
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture_statement)

    assert selected.route_id == route.id
    assert len(statements) == 1
    assert statements[0].lstrip().upper().startswith("SELECT")
    assert "FOR UPDATE" not in statements[0].upper()


@pytest.mark.parametrize(
    "disabled_field",
    ["model", "provider", "protocol", "route"],
)
async def test_disabled_catalog_entities_are_never_returned(
    session: AsyncSession,
    disabled_field: str,
) -> None:
    model, _ = await _add_route(
        session,
        suffix=f"disabled-{disabled_field}",
        model_enabled=disabled_field != "model",
        provider_enabled=disabled_field != "provider",
        protocol_enabled=disabled_field != "protocol",
        route_enabled=disabled_field != "route",
    )

    with pytest.raises(NoRouteAvailable):
        await Router(session).select_route(model, principal())


@pytest.mark.parametrize(
    ("scope", "provider_allowed", "model_allowed", "expected"),
    [
        (ApiKeyScope.ALL, False, False, True),
        (ApiKeyScope.PROVIDERS, True, False, True),
        (ApiKeyScope.PROVIDERS, False, True, False),
        (ApiKeyScope.MODELS, False, True, True),
        (ApiKeyScope.MODELS, True, False, False),
        (ApiKeyScope.PROVIDERS_AND_MODELS, True, True, True),
        (ApiKeyScope.PROVIDERS_AND_MODELS, True, False, False),
        (ApiKeyScope.PROVIDERS_AND_MODELS, False, True, False),
    ],
)
async def test_api_key_scope_is_applied_by_candidate_query(
    session: AsyncSession,
    scope: ApiKeyScope,
    provider_allowed: bool,
    model_allowed: bool,
    expected: bool,
) -> None:
    model, route = await _add_route(
        session,
        suffix=f"scope-{scope}-{provider_allowed}-{model_allowed}",
    )
    api_key = principal(
        scope,
        provider_ids=frozenset({route.provider_id}) if provider_allowed else frozenset(),
        model_ids=frozenset({route.model_id}) if model_allowed else frozenset(),
    )

    if expected:
        selected = await Router(session).select_route(model, api_key)
        assert selected.route_id == route.id
    else:
        with pytest.raises(NoRouteAvailable) as error:
            await Router(session).select_route(model, api_key)
        assert error.value.removed_by_scope is True


async def test_protocol_and_health_filters_are_reported_without_sensitive_details(
    session: AsyncSession,
) -> None:
    model, _ = await _add_route(
        session,
        suffix="transport",
        protocol=Protocol.CLAUDE,
    )

    with pytest.raises(NoRouteAvailable) as transport_error:
        await Router(session).select_route(
            model,
            principal(),
            required_protocol=Protocol.OPENAI,
        )

    assert transport_error.value.code == "no_route_available"
    assert transport_error.value.requested_model == "requested-transport"
    assert transport_error.value.removed_by_transport is True
    assert transport_error.value.removed_by_scope is False
    assert transport_error.value.removed_by_health is False
    assert "provider-transport" not in str(transport_error.value)
    assert "https://" not in str(transport_error.value)

    unhealthy_model, _ = await _add_route(
        session,
        suffix="health",
        runtime_state=RouteRuntimeState.CLOSED,
        disabled_until=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5),
    )

    with pytest.raises(NoRouteAvailable) as health_error:
        await Router(session).select_route(unhealthy_model, principal())

    assert health_error.value.removed_by_health is True
    assert health_error.value.removed_by_scope is False
    assert health_error.value.removed_by_transport is False
    assert "provider-health" not in str(health_error.value)
    assert "https://" not in str(health_error.value)


async def test_no_route_diagnostics_report_multiple_independent_filters(
    session: AsyncSession,
) -> None:
    model, _ = await _add_route(
        session,
        suffix="combined-filters",
        protocol=Protocol.CLAUDE,
        runtime_state=RouteRuntimeState.OPEN,
        disabled_until=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5),
    )
    restricted_principal = principal(ApiKeyScope.PROVIDERS)

    with pytest.raises(NoRouteAvailable) as error:
        await Router(session).select_route(
            model,
            restricted_principal,
            required_protocol=Protocol.OPENAI,
        )

    assert error.value.removed_by_scope is True
    assert error.value.removed_by_transport is True
    assert error.value.removed_by_health is True
    assert "provider-combined-filters" not in str(error.value)
    assert "https://" not in str(error.value)
