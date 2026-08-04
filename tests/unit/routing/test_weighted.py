from __future__ import annotations

import random
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.api_key import ApiKeyPrincipal
from ai_gateway.catalog.repository import CatalogRepository
from ai_gateway.catalog.schemas import ResolvedModel
from ai_gateway.core.enums import ApiKeyScope, Protocol, RouteRuntimeState
from ai_gateway.db.models import Model, ModelAlias, ModelRoute, Provider, ProviderProtocol
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
        upstream_model=f"upstream-{suffix}",
        weight=100,
        enabled=route_enabled,
        runtime_state=runtime_state,
        disabled_until=disabled_until,
    )
    session.add_all([provider_protocol, route])
    await session.flush()
    return (
        ResolvedModel(
            model_id=model.id,
            requested_name=f"requested-{suffix}",
            canonical_name=model.canonical_name,
        ),
        route,
    )


async def _add_shared_alias_routes(
    session: AsyncSession,
) -> tuple[ResolvedModel, ModelRoute, ModelRoute]:
    model_a = Model(
        canonical_name="shared-weighted-a",
        display_name="Shared Weighted A",
        aliases=[ModelAlias(alias="shared-chat", enabled=True)],
    )
    model_b = Model(
        canonical_name="shared-weighted-b",
        display_name="Shared Weighted B",
        aliases=[ModelAlias(alias="shared-chat", enabled=True)],
    )
    provider_a = Provider(name="shared-provider-a", credential_encrypted=b"secret-a")
    provider_b = Provider(name="shared-provider-b", credential_encrypted=b"secret-b")
    route_a = ModelRoute(
        model=model_a,
        provider=provider_a,
        upstream_model="shared-upstream-a",
        weight=1,
    )
    route_b = ModelRoute(
        model=model_b,
        provider=provider_b,
        upstream_model="shared-upstream-b",
        weight=3,
    )
    session.add_all(
        [
            ProviderProtocol(
                provider=provider_a,
                protocol=Protocol.OPENAI,
                base_url="https://shared-a.invalid/v1",
            ),
            route_a,
            ProviderProtocol(
                provider=provider_b,
                protocol=Protocol.OPENAI,
                base_url="https://shared-b.invalid/v1",
            ),
            route_b,
        ]
    )
    await session.flush()
    resolved = await CatalogRepository(session).resolve_model("shared-chat")
    return resolved, route_a, route_b


async def test_shared_alias_weights_routes_across_all_target_models(
    session: AsyncSession,
) -> None:
    resolved, _, route_b = await _add_shared_alias_routes(session)
    router = Router(session, rng=random.Random(20260721))

    model_b_count = 0
    for _ in range(400):
        selected = await router.select_route(
            resolved,
            principal(),
            required_protocol=Protocol.OPENAI,
        )
        model_b_count += selected.model_id == route_b.model_id

    assert 0.70 <= model_b_count / 400 <= 0.80


async def test_shared_alias_honors_model_scope_across_candidates_and_diagnostics(
    session: AsyncSession,
) -> None:
    resolved, route_a, route_b = await _add_shared_alias_routes(session)
    router = Router(session, rng=random.Random(7))
    model_b_principal = principal(
        ApiKeyScope.MODELS,
        model_ids=frozenset({route_b.model_id}),
    )

    assert await router.has_eligible_route(resolved, model_b_principal) is True
    selected = await router.select_route(resolved, model_b_principal)

    assert selected.route_id == route_b.id

    route_a.enabled = False
    await session.flush()
    with pytest.raises(NoRouteAvailable) as error:
        await router.select_route(resolved, principal(ApiKeyScope.MODELS))

    assert error.value.requested_model == "shared-chat"
    assert error.value.removed_by_scope is True


async def test_provider_route_projects_matching_inbound_protocol(
    session: AsyncSession,
) -> None:
    model, route = await _add_route(
        session,
        suffix="multi-protocol-provider",
        protocol=Protocol.OPENAI,
    )
    claude_protocol = ProviderProtocol(
        provider_id=route.provider_id,
        protocol=Protocol.CLAUDE,
        base_url="https://claude.provider.invalid/v1",
    )
    session.add(claude_protocol)
    await session.flush()

    selected = await Router(session).select_route(
        model,
        principal(),
        preferred_protocol=Protocol.CLAUDE,
    )

    assert selected.route_id == route.id
    assert selected.provider_protocol_id == claude_protocol.id
    assert selected.protocol is Protocol.CLAUDE


async def test_conversion_fallback_prefers_openai_over_protocol_creation_order(
    session: AsyncSession,
) -> None:
    model, route = await _add_route(
        session,
        suffix="fallback-order",
        protocol=Protocol.CLAUDE,
    )
    openai_protocol = ProviderProtocol(
        provider_id=route.provider_id,
        protocol=Protocol.OPENAI,
        base_url="https://openai.provider.invalid/v1",
    )
    session.add(openai_protocol)
    await session.flush()

    selected = await Router(session).select_route(
        model,
        principal(),
        preferred_protocol=Protocol.GEMINI,
    )

    assert selected.route_id == route.id
    assert selected.provider_protocol_id == openai_protocol.id
    assert selected.protocol is Protocol.OPENAI


async def test_native_protocol_routes_precede_conversion_then_fall_back_when_excluded(
    session: AsyncSession,
) -> None:
    model = Model(canonical_name="native-first", display_name="Native First")
    native_provider = Provider(name="native-provider", credential_encrypted=b"native")
    native_protocol = ProviderProtocol(
        provider=native_provider,
        protocol=Protocol.CLAUDE,
        base_url="https://native.invalid/v1",
    )
    native_route = ModelRoute(
        model=model,
        provider=native_provider,
        upstream_model="native-model",
        weight=100,
    )
    conversion_provider = Provider(name="conversion-provider", credential_encrypted=b"convert")
    conversion_protocol = ProviderProtocol(
        provider=conversion_provider,
        protocol=Protocol.OPENAI,
        base_url="https://conversion.invalid/v1",
    )
    conversion_route = ModelRoute(
        model=model,
        provider=conversion_provider,
        upstream_model="conversion-model",
        weight=100,
    )
    session.add_all([native_protocol, native_route, conversion_protocol, conversion_route])
    await session.flush()
    router = Router(session, rng=random.Random(0))

    selected = await router.select_route(
        model.id,
        principal(),
        preferred_protocol=Protocol.CLAUDE,
    )
    fallback = await router.select_route(
        model.id,
        principal(),
        preferred_protocol=Protocol.CLAUDE,
        excluded_route_ids={native_route.id},
    )

    assert selected.route_id == native_route.id
    assert selected.protocol is Protocol.CLAUDE
    assert fallback.route_id == conversion_route.id
    assert fallback.protocol is Protocol.OPENAI


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


async def test_maximum_eligible_public_multiplier_uses_scoped_enabled_routes(
    session: AsyncSession,
) -> None:
    model, first_route = await _add_route(session, suffix="public-multiplier-first")
    first_route.provider.public_multiplier = Decimal("1.25")
    second_provider = Provider(
        name="provider-public-multiplier-second",
        credential_encrypted=b"secret",
        public_multiplier=Decimal("2.50"),
    )
    second_protocol = ProviderProtocol(
        provider=second_provider,
        protocol=Protocol.OPENAI,
        base_url="https://public-multiplier-second.invalid/v1",
    )
    second_route = ModelRoute(
        model_id=model.model_id,
        provider=second_provider,
        upstream_model="upstream-public-multiplier-second",
        weight=100,
    )
    session.add_all([second_protocol, second_route])
    await session.flush()

    multiplier = await Router(session).maximum_eligible_public_multiplier(
        model.model_id,
        principal(ApiKeyScope.PROVIDERS, provider_ids=frozenset({first_route.provider_id})),
    )

    assert multiplier == Decimal("1.25")


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
    now = datetime(2026, 7, 30, 12, 0, 0)
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
        disabled_until=now + timedelta(minutes=5),
    )

    with pytest.raises(NoRouteAvailable) as health_error:
        await Router(session, clock=lambda: now).select_route(unhealthy_model, principal())

    assert health_error.value.removed_by_health is True
    assert health_error.value.removed_by_scope is False
    assert health_error.value.removed_by_transport is False
    assert "provider-health" not in str(health_error.value)
    assert "https://" not in str(health_error.value)


async def test_no_route_diagnostics_report_multiple_independent_filters(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 7, 30, 12, 0, 0)
    model, _ = await _add_route(
        session,
        suffix="combined-filters",
        protocol=Protocol.CLAUDE,
        runtime_state=RouteRuntimeState.OPEN,
        disabled_until=now + timedelta(minutes=5),
    )
    restricted_principal = principal(ApiKeyScope.PROVIDERS)

    with pytest.raises(NoRouteAvailable) as error:
        await Router(session, clock=lambda: now).select_route(
            model,
            restricted_principal,
            required_protocol=Protocol.OPENAI,
        )

    assert error.value.removed_by_scope is True
    assert error.value.removed_by_transport is True
    assert error.value.removed_by_health is True
    assert "provider-combined-filters" not in str(error.value)
    assert "https://" not in str(error.value)
