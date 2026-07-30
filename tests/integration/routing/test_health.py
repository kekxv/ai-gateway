from __future__ import annotations

import asyncio
import random
import socket
import ssl
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ai_gateway.auth.api_key import ApiKeyPrincipal
from ai_gateway.catalog.schemas import ResolvedModel
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import ApiKeyScope, Protocol, RouteRuntimeState
from ai_gateway.db.models import Model, ModelRoute, Provider, ProviderProtocol
from ai_gateway.gateway.service import GatewayService
from ai_gateway.gateway.websocket import WebSocketGatewayService
from ai_gateway.routing.health import RouteHealth, health_failure_code, is_health_failure
from ai_gateway.routing.service import Router, router_for_settings
from ai_gateway.routing.types import NoRouteAvailable, RouteCandidate, RouteFailure


def utcnow() -> datetime:
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


def caused_by(exception: BaseException, cause: BaseException) -> BaseException:
    exception.__cause__ = cause
    return exception


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
            upstream_model="health-upstream",
            weight=100,
            enabled=True,
        )
        standby_provider = Provider(
            name=f"health-standby-{suffix}",
            credential_encrypted=b"standby-secret",
            enabled=True,
        )
        standby_protocol = ProviderProtocol(
            provider=standby_provider,
            protocol=Protocol.OPENAI,
            base_url="https://standby.provider.invalid/v1",
            enabled=True,
        )
        standby_route = ModelRoute(
            model=model,
            provider=standby_provider,
            upstream_model="standby-upstream",
            weight=100,
            enabled=True,
        )
        setup_session.add_all([provider_protocol, route, standby_protocol, standby_route])
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
        caused_by(
            httpx.ConnectError("wrapped DNS failure"),
            socket.gaierror("DNS lookup failed"),
        ),
        caused_by(
            httpx.ConnectError("wrapped TLS failure"),
            ssl.SSLError("TLS negotiation failed"),
        ),
    ],
)
def test_network_failures_penalize_route(failure: BaseException) -> None:
    assert is_health_failure(failure) is True
    assert "failed" not in health_failure_code(failure)


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("bare connection failure"),
        ConnectionRefusedError("connection refused"),
        ConnectionResetError("connection reset"),
        httpx.WriteTimeout("write timed out"),
        httpx.PoolTimeout("pool timed out"),
        httpx.WriteError("write failed"),
        httpx.ReadError("read failed"),
        TimeoutError("unspecified timeout"),
        FileNotFoundError("not found"),
        PermissionError("permission denied"),
        OSError("generic operating system error"),
    ],
)
def test_non_connection_failures_do_not_penalize_route(failure: BaseException) -> None:
    assert is_health_failure(failure) is False


@pytest.mark.parametrize("close_code", [4000, 4001, 4100, 4400, 4401, 4402, 4999])
def test_websocket_application_closes_do_not_penalize_route(close_code: int) -> None:
    assert is_health_failure(RouteFailure(error_code=f"websocket_close_{close_code}")) is False


@pytest.mark.parametrize("close_code", [1002, 1006, 1011, 1012, 1013, 1014, 1015])
def test_websocket_protocol_network_and_service_closes_penalize_route(close_code: int) -> None:
    assert is_health_failure(RouteFailure(error_code=f"websocket_close_{close_code}")) is True


async def test_half_open_application_websocket_close_leaves_probe_state_unchanged(
    test_engine: AsyncEngine,
    committed_route: tuple[ResolvedModel, int],
) -> None:
    _, route_id = committed_route
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        route = await _load_route(session, route_id)
        route.runtime_state = RouteRuntimeState.HALF_OPEN
        route.consecutive_failures = 3
        await session.commit()

        changed = await RouteHealth(session).record_failure(
            route_id,
            RouteFailure(error_code="websocket_close_4400"),
        )
        route = await _load_route(session, route_id)

    assert changed is False
    assert route.runtime_state is RouteRuntimeState.HALF_OPEN
    assert route.consecutive_failures == 3


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
            await RouteHealth(session, failure_threshold=3).record_failure(route_id, status_code)

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


async def _provider_count(session: AsyncSession, name: str) -> int:
    return await session.scalar(
        select(func.count()).select_from(Provider).where(Provider.name == name)
    )


@pytest.mark.parametrize("operation", ["failure", "success"])
async def test_health_mutation_does_not_flush_or_commit_caller_writes(
    test_engine: AsyncEngine,
    committed_route: tuple[ResolvedModel, int],
    operation: str,
) -> None:
    _, route_id = committed_route
    mutation_sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    unrelated_name = f"unrelated-health-{operation}-{uuid4().hex}"

    if operation == "success":
        async with mutation_sessions() as setup_session:
            await RouteHealth(
                setup_session,
                mutation_session_factory=mutation_sessions,
            ).record_failure(route_id, 500)

    async with AsyncSession(test_engine, expire_on_commit=False) as caller_session:
        unrelated = Provider(
            name=unrelated_name,
            credential_encrypted=b"unrelated",
        )
        caller_session.add(unrelated)
        health = RouteHealth(
            caller_session,
            mutation_session_factory=mutation_sessions,
        )

        if operation == "failure":
            await health.record_failure(route_id, 500)
        else:
            await health.record_success(route_id)

        assert unrelated.id is None
        async with mutation_sessions() as observer:
            route = await _load_route(observer, route_id)
            assert await _provider_count(observer, unrelated_name) == 0
            if operation == "failure":
                assert route.consecutive_failures == 1
            else:
                assert route.consecutive_failures == 0
                assert route.runtime_state is RouteRuntimeState.CLOSED

        await caller_session.rollback()

    async with mutation_sessions() as observer:
        assert await _provider_count(observer, unrelated_name) == 0


async def test_runtime_route_threshold_and_cooldown_are_applied(
    test_engine: AsyncEngine,
    committed_route: tuple[ResolvedModel, int],
) -> None:
    _, route_id = committed_route
    settings = Settings(
        _env_file=None,
        environment="test",
        jwt_secret="route-settings-secret-at-least-32-bytes",
        encryption_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        route_failure_threshold=1,
        route_cooldown_seconds=7,
    )
    before = utcnow()
    async with AsyncSession(test_engine, expire_on_commit=False) as caller:
        changed = await router_for_settings(caller, settings).record_failure(route_id, 500)
    assert changed

    async with AsyncSession(test_engine, expire_on_commit=False) as observer:
        route = await _load_route(observer, route_id)
    assert route.runtime_state is RouteRuntimeState.OPEN
    assert route.consecutive_failures == 1
    assert route.disabled_until is not None
    assert before + timedelta(seconds=6) <= route.disabled_until <= utcnow() + timedelta(seconds=8)


async def test_http_sse_and_websocket_services_own_configured_router_health(
    test_engine: AsyncEngine,
) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        jwt_secret="route-settings-secret-at-least-32-bytes",
        encryption_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        route_failure_threshold=2,
        route_cooldown_seconds=11,
    )
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        http_and_sse = GatewayService(
            session=session,
            settings=settings,
            billing_service=object(),  # type: ignore[arg-type]
            audit_service=object(),  # type: ignore[arg-type]
            http_client_factory=object(),  # type: ignore[arg-type]
        )
        websocket = WebSocketGatewayService(
            session=session,
            settings=settings,
            billing_service=object(),  # type: ignore[arg-type]
            audit_service=object(),  # type: ignore[arg-type]
        )

        for route_router in (
            http_and_sse._router_factory(session),
            websocket._router_factory(session),
        ):
            assert isinstance(route_router, Router)
            assert route_router._failure_threshold == 2
            assert route_router._cooldown == timedelta(seconds=11)


async def test_half_open_claim_isolated_from_caller_transaction_and_returns_fresh_state(
    test_engine: AsyncEngine,
    committed_route: tuple[ResolvedModel, int],
    all_scope_principal: ApiKeyPrincipal,
) -> None:
    model, route_id = committed_route
    mutation_sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    async with mutation_sessions() as setup_session:
        route = await _load_route(setup_session, route_id)
        route.runtime_state = RouteRuntimeState.OPEN
        route.consecutive_failures = 3
        route.disabled_until = utcnow() - timedelta(seconds=1)
        await setup_session.commit()

    unrelated_name = f"unrelated-claim-{uuid4().hex}"
    async with AsyncSession(test_engine, expire_on_commit=False) as caller_session:
        unrelated = Provider(name=unrelated_name, credential_encrypted=b"unrelated")
        caller_session.add(unrelated)
        selected = await Router(
            caller_session,
            mutation_session_factory=mutation_sessions,
        ).select_route(model, all_scope_principal)

        assert unrelated.id is None
        assert selected.runtime_state is RouteRuntimeState.HALF_OPEN
        assert selected.disabled_until is None
        async with mutation_sessions() as observer:
            route = await _load_route(observer, route_id)
            assert route.runtime_state is RouteRuntimeState.HALF_OPEN
            assert route.disabled_until is None
            assert await _provider_count(observer, unrelated_name) == 0

        await caller_session.rollback()

    async with mutation_sessions() as observer:
        assert await _provider_count(observer, unrelated_name) == 0


async def test_failed_half_open_claim_does_not_commit_caller_work(
    test_engine: AsyncEngine,
    committed_route: tuple[ResolvedModel, int],
) -> None:
    _, route_id = committed_route
    mutation_sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    async with mutation_sessions() as setup_session:
        route = await _load_route(setup_session, route_id)
        route.runtime_state = RouteRuntimeState.HALF_OPEN
        route.disabled_until = None
        await setup_session.commit()

    unrelated_name = f"unrelated-failed-claim-{uuid4().hex}"
    async with AsyncSession(test_engine, expire_on_commit=False) as caller_session:
        unrelated = Provider(name=unrelated_name, credential_encrypted=b"unrelated")
        caller_session.add(unrelated)
        router = Router(
            caller_session,
            mutation_session_factory=mutation_sessions,
        )

        claimed = await router._claim_half_open(route_id, utcnow())

        assert claimed is False
        assert unrelated.id is None
        async with mutation_sessions() as observer:
            assert await _provider_count(observer, unrelated_name) == 0
        await caller_session.rollback()

    async with mutation_sessions() as observer:
        assert await _provider_count(observer, unrelated_name) == 0


async def test_only_route_for_model_is_not_disabled_even_after_threshold_failures(
    test_engine: AsyncEngine,
) -> None:
    """When a route is the only enabled route for a model, it should not be disabled."""
    suffix = uuid4().hex
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as setup_session:
        model = Model(
            canonical_name=f"only-route-model-{suffix}",
            display_name="Only Route Model",
            enabled=True,
        )
        provider = Provider(
            name=f"only-route-provider-{suffix}",
            credential_encrypted=b"secret",
            enabled=True,
        )
        provider_protocol = ProviderProtocol(
            provider=provider,
            protocol=Protocol.OPENAI,
            base_url="https://only.provider.invalid/v1",
            enabled=True,
        )
        route = ModelRoute(
            model=model,
            provider=provider,
            upstream_model="only-upstream",
            weight=100,
            enabled=True,
        )
        setup_session.add_all([provider_protocol, route])
        await setup_session.commit()
        route_id = route.id

    for status in (500, 502, 503):
        async with AsyncSession(test_engine, expire_on_commit=False) as session:
            await RouteHealth(session, failure_threshold=3).record_failure(route_id, status)

    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        route = await _load_route(session, route_id)

    assert route.consecutive_failures == 3
    assert route.runtime_state is RouteRuntimeState.CLOSED
    assert route.disabled_until is None
    assert route.last_error_code == "http_503"
    assert route.last_error_at is not None
