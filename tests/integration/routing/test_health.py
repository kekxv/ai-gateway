from __future__ import annotations

import asyncio
import random
import socket
import ssl
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ai_gateway.auth.api_key import ApiKeyPrincipal
from ai_gateway.catalog.schemas import ResolvedModel
from ai_gateway.core.enums import ApiKeyScope, Protocol, RouteRuntimeState
from ai_gateway.db.models import Model, ModelRoute, Provider, ProviderProtocol
from ai_gateway.routing.health import RouteHealth, health_failure_code, is_health_failure
from ai_gateway.routing.service import Router
from ai_gateway.routing.types import NoRouteAvailable, RouteCandidate


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def all_scope_principal() -> ApiKeyPrincipal:
    return ApiKeyPrincipal(api_key_id=1, user_id=1, scope=ApiKeyScope.ALL)


@pytest_asyncio.fixture
async def committed_route(
    test_engine: AsyncEngine,
) -> AsyncIterator[tuple[ResolvedModel, int]]:
    suffix = uuid4().hex
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as setup_session:
        model = Model(
            canonical_name=f"health-model-{suffix}",
            display_name="Health Model",
            enabled=True,
        )
        provider = Provider(
            name=f"health-provider-{suffix}",
            credential_encrypted=b"secret",
            enabled=True,
        )
        provider_protocol = ProviderProtocol(
            provider=provider,
            protocol=Protocol.OPENAI,
            base_url="https://health.provider.invalid/v1",
            enabled=True,
        )
        route = ModelRoute(
            model=model,
            provider=provider,
            provider_protocol=provider_protocol,
            upstream_model="health-upstream",
            weight=100,
            enabled=True,
        )
        setup_session.add(route)
        await setup_session.commit()
        resolved = ResolvedModel(
            model_id=model.id,
            requested_name="health-requested",
            canonical_name=model.canonical_name,
        )
        route_id = route.id

    yield resolved, route_id


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
def test_client_http_failures_do_not_penalize_route(status_code: int) -> None:
    assert is_health_failure(status_code) is False
    assert health_failure_code(status_code) == f"http_{status_code}"


@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
def test_retryable_http_failures_penalize_route(status_code: int) -> None:
    assert is_health_failure(status_code) is True
    assert health_failure_code(status_code) == f"http_{status_code}"


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectTimeout("connect timed out"),
        httpx.ReadTimeout("read timed out"),
        socket.gaierror("DNS lookup failed"),
        ssl.SSLError("TLS negotiation failed"),
    ],
)
def test_network_failures_penalize_route(failure: BaseException) -> None:
    assert is_health_failure(failure) is True
    assert "failed" not in health_failure_code(failure)


async def _load_route(session: AsyncSession, route_id: int) -> ModelRoute:
    route = await session.scalar(
        select(ModelRoute)
        .where(ModelRoute.id == route_id)
        .execution_options(populate_existing=True)
    )
    assert route is not None
    return route


async def test_non_penalizing_failure_leaves_health_unchanged(
    test_engine: AsyncEngine,
    committed_route: tuple[ResolvedModel, int],
) -> None:
    _, route_id = committed_route
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        changed = await RouteHealth(session).record_failure(route_id, 422)
        route = await _load_route(session, route_id)

    assert changed is False
    assert route.consecutive_failures == 0
    assert route.runtime_state is RouteRuntimeState.CLOSED
    assert route.last_error_code is None


async def test_concurrent_third_failure_opens_route_atomically(
    test_engine: AsyncEngine,
    committed_route: tuple[ResolvedModel, int],
) -> None:
    _, route_id = committed_route

    async def fail_once(status_code: int) -> None:
        async with AsyncSession(test_engine, expire_on_commit=False) as session:
            await RouteHealth(session).record_failure(route_id, status_code)

    before = utcnow()
    await asyncio.gather(fail_once(500), fail_once(502), fail_once(503))

    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        route = await _load_route(session, route_id)

    assert route.consecutive_failures == 3
    assert route.runtime_state is RouteRuntimeState.OPEN
    assert route.disabled_until is not None
    assert (
        before + timedelta(seconds=55) <= route.disabled_until <= utcnow() + timedelta(seconds=65)
    )
    assert route.last_error_code in {"http_500", "http_502", "http_503"}
    assert route.last_error_at is not None


async def test_success_resets_failures_state_and_error_metadata(
    test_engine: AsyncEngine,
    committed_route: tuple[ResolvedModel, int],
) -> None:
    _, route_id = committed_route
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        health = RouteHealth(session)
        await health.record_failure(route_id, 500)
        await health.record_success(route_id)
        route = await _load_route(session, route_id)

    assert route.consecutive_failures == 0
    assert route.runtime_state is RouteRuntimeState.CLOSED
    assert route.disabled_until is None
    assert route.last_error_code is None
    assert route.last_error_at is None


async def test_only_one_caller_claims_half_open_probe_after_cooldown(
    test_engine: AsyncEngine,
    committed_route: tuple[ResolvedModel, int],
    all_scope_principal: ApiKeyPrincipal,
) -> None:
    model, route_id = committed_route
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        route = await _load_route(session, route_id)
        route.runtime_state = RouteRuntimeState.OPEN
        route.consecutive_failures = 3
        route.disabled_until = utcnow() - timedelta(seconds=1)
        await session.commit()

    ready = asyncio.Event()
    entered = 0
    entered_lock = asyncio.Lock()

    async def select_once(seed: int) -> RouteCandidate | NoRouteAvailable:
        nonlocal entered
        async with AsyncSession(test_engine, expire_on_commit=False) as session:
            async with entered_lock:
                entered += 1
                if entered == 2:
                    ready.set()
            await ready.wait()
            try:
                return await Router(session, rng=random.Random(seed)).select_route(
                    model,
                    all_scope_principal,
                )
            except NoRouteAvailable as exc:
                return exc

    results = await asyncio.gather(select_once(1), select_once(2))

    assert sum(isinstance(result, RouteCandidate) for result in results) == 1
    assert sum(isinstance(result, NoRouteAvailable) for result in results) == 1
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        route = await _load_route(session, route_id)
    assert route.runtime_state is RouteRuntimeState.HALF_OPEN


async def test_half_open_failure_reopens_and_success_closes(
    test_engine: AsyncEngine,
    committed_route: tuple[ResolvedModel, int],
) -> None:
    _, route_id = committed_route
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        route = await _load_route(session, route_id)
        route.runtime_state = RouteRuntimeState.HALF_OPEN
        route.consecutive_failures = 3
        route.disabled_until = None
        await session.commit()

        before = utcnow()
        await RouteHealth(session).record_failure(route_id, 500)
        route = await _load_route(session, route_id)
        assert route.runtime_state is RouteRuntimeState.OPEN
        assert route.disabled_until is not None
        assert route.disabled_until >= before + timedelta(seconds=55)

        route.runtime_state = RouteRuntimeState.HALF_OPEN
        await session.commit()
        await RouteHealth(session).record_success(route_id)
        route = await _load_route(session, route_id)

    assert route.runtime_state is RouteRuntimeState.CLOSED
    assert route.consecutive_failures == 0
    assert route.disabled_until is None
