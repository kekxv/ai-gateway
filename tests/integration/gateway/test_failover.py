from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import httpx
import orjson
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ai_gateway.audit.service import AuditService, RequestContext, RequestFailure, RequestResult
from ai_gateway.billing.service import (
    BalanceReservation,
    BillingService,
    InsufficientBalance,
    SettlementResult,
)
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import (
    ApiKeyScope,
    LedgerKind,
    Protocol,
    RequestStatus,
    RouteRuntimeState,
)
from ai_gateway.core.security import encrypt_secret
from ai_gateway.db.models import (
    Account,
    ApiKey,
    LedgerEntry,
    Model,
    ModelAlias,
    ModelRoute,
    Provider,
    ProviderProtocol,
    RequestLog,
    User,
)
from ai_gateway.gateway.dependencies import get_gateway_service
from ai_gateway.gateway.openai import router as openai_router
from ai_gateway.gateway.service import (
    GatewayService,
    is_provider_quota_exhausted_response,
    is_retryable_failure,
)
from ai_gateway.routing.service import Router
from ai_gateway.routing.types import RouteCandidate


@dataclass
class FakeBilling:
    async def reserve_balance(self, **kwargs: Any) -> BalanceReservation:
        return BalanceReservation(
            ledger_entry_id=1,
            account_id=1,
            user_id=kwargs["user_id"],
            request_id=str(kwargs["request_id"]),
            idempotency_key=kwargs["idempotency_key"],
            amount=Decimal("1"),
            balance_after=Decimal("9"),
        )

    async def settle_request(self, **kwargs: Any) -> SettlementResult:
        cost = kwargs.get("cost", Decimal("0"))
        return SettlementResult(
            account_id=1,
            request_id="request",
            reserved_amount=Decimal("1"),
            actual_cost=cost,
            charged_amount=cost,
            balance=Decimal("9"),
            total_spent=cost,
            exhausted=False,
        )


@dataclass
class FakeAudit:
    completed: RequestResult | None = None
    failed: RequestFailure | None = None

    async def start_request(
        self,
        _: RequestContext,
        __: bytes,
        *,
        request_id: UUID | None = None,
    ) -> UUID:
        return request_id or uuid4()

    async def complete_request(self, _: UUID, result: RequestResult) -> None:
        self.completed = result

    async def fail_request(self, _: UUID, failure: RequestFailure) -> None:
        self.failed = failure


class FakeHttpClients:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def client_for(
        self,
        _: str | httpx.URL,
        *,
        provider_id: int | None = None,
        proxy_config_encrypted: bytes | None = None,
    ) -> httpx.AsyncClient:
        return self.client


def test_failover_retries_only_intended_statuses_and_transport_failures() -> None:
    assert is_retryable_failure(status_code=408)
    assert is_retryable_failure(status_code=429)
    assert is_retryable_failure(status_code=500)
    assert is_retryable_failure(status_code=599)
    assert not is_retryable_failure(status_code=400)
    assert not is_retryable_failure(status_code=401)
    assert is_retryable_failure(exception=httpx.ConnectError("offline"))
    assert is_retryable_failure(exception=httpx.ReadTimeout("slow"))
    assert is_retryable_failure(exception=httpx.ReadError("broken read"))
    assert is_retryable_failure(exception=httpx.WriteError("broken write"))
    assert is_retryable_failure(exception=httpx.CloseError("broken close"))
    assert not is_retryable_failure(exception=ValueError("bad request"))


def test_insufficient_user_quota_response_is_classified_for_failover() -> None:
    response = httpx.Response(
        403,
        json={"error": {"code": "insufficient_user_quota"}},
    )

    assert is_provider_quota_exhausted_response(response) is True
    assert is_provider_quota_exhausted_response(httpx.Response(403, json={"error": {}})) is False
    assert is_provider_quota_exhausted_response(httpx.Response(403, content=b"not-json")) is False


@pytest.mark.parametrize(
    ("first_status", "first_error", "expected_error_code"),
    [
        (503, {"message": "temporary"}, "http_503"),
        (403, {"code": "insufficient_user_quota"}, "http_403"),
    ],
)
async def test_mysql_backed_failover_uses_each_route_once_and_audits_attempt_order(
    test_engine: AsyncEngine,
    first_status: int,
    first_error: dict[str, str],
    expected_error_code: str,
) -> None:
    suffix = uuid4().hex
    raw_key = f"sk-gw-failover-{suffix}"
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=test_engine.url.render_as_string(hide_password=False),
        jwt_secret="gateway-failover-jwt-secret",
        encryption_key=Fernet.generate_key().decode(),
    )
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as setup:
        user = User(email=f"failover-{suffix}@example.com", password_hash="unused")
        user.api_keys.append(
            ApiKey(
                name="failover",
                key_prefix=raw_key[:12],
                key_hash=sha256(raw_key.encode()).digest(),
                scope=ApiKeyScope.ALL,
            )
        )
        model = Model(
            canonical_name=f"canonical-{suffix}",
            display_name="Failover",
            input_price_per_million=Decimal("0.1"),
            output_price_per_million=Decimal("0.2"),
        )
        alias = ModelAlias(alias=f"alias-{suffix}")
        model.aliases.append(alias)
        encrypted = encrypt_secret(
            orjson.dumps({"api_key": "provider-secret"}).decode(),
            settings=settings,
        )
        first_provider = Provider(name=f"first-{suffix}", credential_encrypted=encrypted)
        second_provider = Provider(name=f"second-{suffix}", credential_encrypted=encrypted)
        first_protocol = ProviderProtocol(
            protocol=Protocol.OPENAI,
            base_url=f"https://first-{suffix}.example/v1",
        )
        second_protocol = ProviderProtocol(
            protocol=Protocol.OPENAI,
            base_url=f"https://second-{suffix}.example/v1",
        )
        first_provider.protocols.append(first_protocol)
        second_provider.protocols.append(second_protocol)
        setup.add_all((user, model, first_provider, second_provider))
        await setup.flush()
        first_route = ModelRoute(
            model_id=model.id,
            provider_id=first_provider.id,
            upstream_model="first-native",
            weight=10000,
        )
        second_route = ModelRoute(
            model_id=model.id,
            provider_id=second_provider.id,
            upstream_model="second-native",
            weight=1,
        )
        setup.add_all((first_route, second_route))
        await setup.commit()
        first_route_id = first_route.id
        second_route_id = second_route.id
        alias_name = alias.alias

    seen_models: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = orjson.loads(request.content)
        seen_models.append(payload["model"])
        if request.url.host and request.url.host.startswith("first-"):
            return httpx.Response(first_status, json={"error": first_error})
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_failover",
                "object": "chat.completion",
                "model": "second-native",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    audit = FakeAudit()
    async with session_factory() as gateway_session:
        service = GatewayService(
            session=gateway_session,
            settings=settings,
            billing_service=FakeBilling(),  # type: ignore[arg-type]
            audit_service=audit,  # type: ignore[arg-type]
            http_client_factory=FakeHttpClients(upstream_client),
            router_factory=lambda session: Router(session, rng=random.Random(1)),
        )
        app = FastAPI()
        app.include_router(openai_router)
        app.dependency_overrides[get_gateway_service] = lambda: service
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"authorization": f"Bearer {raw_key}"},
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": alias_name,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 8,
                },
            )
    await upstream_client.aclose()

    assert response.status_code == 200, response.text
    assert seen_models == ["first-native", "second-native"]
    assert audit.completed is not None
    attempts = audit.completed.metadata["attempts"]
    assert [attempt["route_id"] for attempt in attempts] == [first_route_id, second_route_id]
    assert audit.completed.model_route_id == second_route_id
    async with session_factory() as verify:
        refreshed_first = await verify.get(ModelRoute, first_route_id)
        refreshed_second = await verify.get(ModelRoute, second_route_id)
        assert refreshed_first is not None
        assert refreshed_second is not None
        assert refreshed_first.consecutive_failures == 1
        assert refreshed_first.last_error_code == expected_error_code
        assert refreshed_second.consecutive_failures == 0


class StageRouter:
    def __init__(self, route: RouteCandidate, stage: str) -> None:
        self.route = route
        self.stage = stage
        self.entered = asyncio.Event()
        self.selection_calls = 0

    async def select_route(self, *_: Any, **__: Any) -> RouteCandidate:
        self.selection_calls += 1
        if self.selection_calls > 1 and self.stage == "route_selection":
            raise asyncio.CancelledError
        if self.selection_calls > 1 and self.stage == "task_cancel_route_selection":
            self.entered.set()
            await asyncio.Future()
        return self.route

    async def record_success(self, _: int) -> bool:
        return True

    async def record_failure(self, _: int, __: object) -> bool:
        return True


class StageAudit:
    def __init__(self, service: AuditService, stage: str) -> None:
        self.service = service
        self.stage = stage

    async def start_request(
        self,
        context: RequestContext,
        body: bytes,
        *,
        request_id: UUID | None = None,
    ) -> UUID:
        result = await self.service.start_request(context, body, request_id=request_id)
        if self.stage == "audit_start":
            raise asyncio.CancelledError
        return result

    async def complete_request(self, request_id: UUID, result: RequestResult) -> None:
        if self.stage == "audit_completion":
            raise asyncio.CancelledError
        await self.service.complete_request(request_id, result)

    async def fail_request(self, request_id: UUID, failure: RequestFailure) -> None:
        await self.service.fail_request(request_id, failure)


class StageBilling:
    def __init__(self, service: BillingService, stage: str) -> None:
        self.service = service
        self.stage = stage
        self.settlement_calls = 0
        self.post_commit_cancellation = asyncio.CancelledError(
            "settlement committed before cancellation"
        )

    async def reserve_balance(self, **kwargs: Any) -> BalanceReservation:
        return await self.service.reserve_balance(**kwargs)

    async def settle_request(self, **kwargs: Any) -> SettlementResult:
        self.settlement_calls += 1
        if self.stage == "settlement" and self.settlement_calls == 1:
            raise asyncio.CancelledError
        result = await self.service.settle_request(**kwargs)
        if self.stage == "settlement_post_commit" and self.settlement_calls == 1:
            raise self.post_commit_cancellation
        return result


def gateway_request(raw_key: str, model: str, *, stream: bool = False) -> FastAPIRequest:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "cancel me"}],
        "max_tokens": 8,
    }
    if stream:
        payload["stream"] = True
    body = orjson.dumps(payload)
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return FastAPIRequest(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/chat/completions",
            "raw_path": b"/v1/chat/completions",
            "query_string": b"",
            "headers": [
                (b"authorization", f"Bearer {raw_key}".encode()),
                (b"content-type", b"application/json"),
            ],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
        },
        receive,
    )


@pytest.mark.parametrize("failure_stage", ["token_estimate_cancellation", "insufficient_balance"])
async def test_pre_reservation_failure_releases_selected_half_open_probe(
    test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    import ai_gateway.gateway.service as gateway_module

    suffix = uuid4().hex
    raw_key = f"sk-gw-setup-failure-{suffix}"
    now = datetime.now(UTC).replace(tzinfo=None)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=test_engine.url.render_as_string(hide_password=False),
        jwt_secret="gateway-setup-failure-jwt-secret",
        encryption_key=Fernet.generate_key().decode(),
    )
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sessions() as setup:
        user = User(email=f"setup-failure-{suffix}@example.com", password_hash="unused")
        user.api_keys.append(
            ApiKey(
                name="setup-failure",
                key_prefix=raw_key[:12],
                key_hash=sha256(raw_key.encode()).digest(),
                scope=ApiKeyScope.ALL,
            )
        )
        model = Model(
            canonical_name=f"setup-failure-model-{suffix}",
            display_name="Setup Failure Model",
            input_price_per_million=Decimal("1"),
            output_price_per_million=Decimal("2"),
        )
        alias = ModelAlias(alias=f"setup-failure-alias-{suffix}")
        model.aliases.append(alias)
        provider = Provider(
            name=f"setup-failure-provider-{suffix}",
            credential_encrypted=encrypt_secret("{}", settings=settings),
            public_multiplier=Decimal("2.75"),
        )
        protocol = ProviderProtocol(
            provider=provider,
            protocol=Protocol.OPENAI,
            base_url="https://setup-failure.example/v1",
        )
        route = ModelRoute(
            model=model,
            provider=provider,
            upstream_model="setup-failure-native",
            weight=100,
            runtime_state=RouteRuntimeState.OPEN,
            disabled_until=now - timedelta(seconds=1),
            consecutive_failures=3,
            last_error_code="connect_timeout",
        )
        setup.add_all([user, protocol, route])
        await setup.commit()
        route_id = route.id
        alias_name = alias.alias

    setup_failure: BaseException
    if failure_stage == "token_estimate_cancellation":
        setup_failure = asyncio.CancelledError("cancel during token estimation")

        async def fail_estimate(*_: Any, **__: Any) -> int:
            raise setup_failure

        monkeypatch.setattr(gateway_module, "estimate_request_tokens_async", fail_estimate)
    else:
        setup_failure = InsufficientBalance(required=Decimal("1"), available=Decimal("0"))

    class SetupFailureBilling(FakeBilling):
        async def reserve_balance(self, **kwargs: Any) -> BalanceReservation:
            if failure_stage == "token_estimate_cancellation":
                pytest.fail("token-estimation cancellation must precede reservation")
            assert kwargs["provider_public_multiplier"] == Decimal("2.75")
            raise setup_failure

    upstream_calls = 0

    async def unexpected_upstream(_: httpx.Request) -> httpx.Response:
        nonlocal upstream_calls
        upstream_calls += 1
        return httpx.Response(500)

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(unexpected_upstream))
    async with sessions() as gateway_session:
        service = GatewayService(
            session=gateway_session,
            settings=settings,
            billing_service=SetupFailureBilling(),  # type: ignore[arg-type]
            audit_service=FakeAudit(),  # type: ignore[arg-type]
            http_client_factory=FakeHttpClients(upstream_client),
            router_factory=lambda session: Router(session),
        )
        with pytest.raises(type(setup_failure)) as captured:
            await service.handle(gateway_request(raw_key, alias_name), Protocol.OPENAI)
    await upstream_client.aclose()

    assert captured.value is setup_failure
    assert upstream_calls == 0
    async with sessions() as verify:
        route = await verify.get(ModelRoute, route_id)
        assert route is not None
        assert route.runtime_state is RouteRuntimeState.OPEN
        assert route.disabled_until is not None
        assert route.disabled_until <= datetime.now(UTC).replace(tzinfo=None)
        assert route.consecutive_failures == 3
        assert route.last_error_code == "connect_timeout"


@pytest.mark.parametrize(
    "cancellation_stage",
    ["send", "stream_prefetch", "session_release"],
)
async def test_retry_selected_half_open_probe_is_released_when_cancelled(
    test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    cancellation_stage: str,
) -> None:
    import ai_gateway.gateway.service as gateway_module

    suffix = uuid4().hex
    raw_key = f"sk-gw-retry-half-open-{suffix}"
    now = datetime.now(UTC).replace(tzinfo=None)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=test_engine.url.render_as_string(hide_password=False),
        jwt_secret="gateway-retry-half-open-jwt-secret",
        encryption_key=Fernet.generate_key().decode(),
    )
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sessions() as setup:
        user = User(email=f"retry-half-open-{suffix}@example.com", password_hash="unused")
        user.api_keys.append(
            ApiKey(
                name="retry-half-open",
                key_prefix=raw_key[:12],
                key_hash=sha256(raw_key.encode()).digest(),
                scope=ApiKeyScope.ALL,
            )
        )
        model = Model(
            canonical_name=f"retry-half-open-model-{suffix}",
            display_name="Retry Half Open Model",
            input_price_per_million=Decimal("1"),
            output_price_per_million=Decimal("2"),
        )
        alias = ModelAlias(alias=f"retry-half-open-alias-{suffix}")
        model.aliases.append(alias)
        first_provider = Provider(
            name=f"retry-half-open-first-{suffix}",
            credential_encrypted=encrypt_secret("{}", settings=settings),
        )
        first_protocol = ProviderProtocol(
            provider=first_provider,
            protocol=Protocol.OPENAI,
            base_url="https://retry-first.example/v1",
        )
        first_route = ModelRoute(
            model=model,
            provider=first_provider,
            upstream_model="retry-first-native",
            weight=100,
        )
        retry_provider = Provider(
            name=f"retry-half-open-second-{suffix}",
            credential_encrypted=encrypt_secret("{}", settings=settings),
        )
        retry_protocol = ProviderProtocol(
            provider=retry_provider,
            protocol=Protocol.OPENAI,
            base_url="https://retry-second.example/v1",
        )
        retry_route = ModelRoute(
            model=model,
            provider=retry_provider,
            upstream_model="retry-second-native",
            weight=100,
            runtime_state=RouteRuntimeState.OPEN,
            disabled_until=now - timedelta(seconds=1),
            consecutive_failures=3,
            last_error_code="connect_timeout",
        )
        setup.add_all(
            [
                user,
                first_protocol,
                first_route,
                retry_protocol,
                retry_route,
            ]
        )
        await setup.commit()
        retry_route_id = retry_route.id
        alias_name = alias.alias
        initial_candidate = RouteCandidate(
            route_id=first_route.id,
            model_id=model.id,
            provider_id=first_provider.id,
            provider_protocol_id=first_protocol.id,
            protocol=Protocol.OPENAI,
            base_url=first_protocol.base_url,
            websocket_url=None,
            upstream_model=first_route.upstream_model,
            weight=first_route.weight,
            provider_credential_encrypted=first_provider.credential_encrypted,
        )

    class RetrySelectingRouter:
        def __init__(self, session: Any) -> None:
            self.delegate = Router(session)
            self.selection_calls = 0
            self.retry_candidate: RouteCandidate | None = None

        async def select_route(self, *args: Any, **kwargs: Any) -> RouteCandidate:
            self.selection_calls += 1
            if self.selection_calls == 1:
                return initial_candidate
            selected = await self.delegate.select_route(*args, **kwargs)
            self.retry_candidate = selected
            return selected

        async def record_success(self, route_id: int) -> bool:
            return await self.delegate.record_success(route_id)

        async def record_failure(self, route_id: int, failure: object) -> bool:
            return await self.delegate.record_failure(route_id, failure)

        async def release_half_open(self, route_id: int) -> bool:
            return await self.delegate.release_half_open(route_id)

        async def maximum_eligible_public_multiplier(
            self,
            *args: Any,
            **kwargs: Any,
        ) -> Decimal | None:
            return await self.delegate.maximum_eligible_public_multiplier(*args, **kwargs)

    cancellation = asyncio.CancelledError(f"cancel retry-selected {cancellation_stage}")
    upstream_calls = 0

    async def cancel_retry_send(_: httpx.Request) -> httpx.Response:
        nonlocal upstream_calls
        upstream_calls += 1
        if upstream_calls == 1:
            return httpx.Response(503)
        if cancellation_stage == "send":
            raise cancellation
        return httpx.Response(200)

    if cancellation_stage == "stream_prefetch":

        async def cancelled_stream() -> Any:
            raise cancellation
            yield b"unreachable"

        monkeypatch.setattr(
            gateway_module,
            "stream_gateway_response",
            lambda *_: cancelled_stream(),
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(cancel_retry_send))
    async with sessions() as gateway_session:
        route_router = RetrySelectingRouter(gateway_session)
        if cancellation_stage == "session_release":
            original_release_read_session = gateway_module._release_read_session
            release_cancelled = False

            async def cancel_retry_session_release(session: object) -> None:
                nonlocal release_cancelled
                if route_router.retry_candidate is not None and not release_cancelled:
                    release_cancelled = True
                    raise cancellation
                await original_release_read_session(session)

            monkeypatch.setattr(
                gateway_module,
                "_release_read_session",
                cancel_retry_session_release,
            )
        service = GatewayService(
            session=gateway_session,
            settings=settings,
            billing_service=FakeBilling(),  # type: ignore[arg-type]
            audit_service=FakeAudit(),  # type: ignore[arg-type]
            http_client_factory=FakeHttpClients(upstream_client),
            router_factory=lambda _: route_router,  # type: ignore[arg-type]
        )
        with pytest.raises(asyncio.CancelledError) as captured:
            await service.handle(
                gateway_request(
                    raw_key,
                    alias_name,
                    stream=cancellation_stage == "stream_prefetch",
                ),
                Protocol.OPENAI,
            )
    await upstream_client.aclose()

    assert captured.value is cancellation
    assert upstream_calls == (1 if cancellation_stage == "session_release" else 2)
    assert route_router.selection_calls == 2
    assert route_router.retry_candidate is not None
    assert route_router.retry_candidate.route_id == retry_route_id
    assert route_router.retry_candidate.runtime_state is RouteRuntimeState.HALF_OPEN
    async with sessions() as verify:
        released_route = await verify.get(ModelRoute, retry_route_id)
        assert released_route is not None
        assert released_route.runtime_state is RouteRuntimeState.OPEN
        assert released_route.disabled_until is not None
        assert released_route.disabled_until <= datetime.now(UTC).replace(tzinfo=None)
        assert released_route.consecutive_failures == 3
        assert released_route.last_error_code == "connect_timeout"


@pytest.mark.parametrize(
    "stage",
    [
        "audit_start",
        "route_selection",
        "task_cancel_route_selection",
        "upstream_send",
        "settlement",
        "settlement_post_commit",
        "audit_completion",
    ],
)
async def test_cancellation_after_reservation_is_shielded_and_terminal(
    test_engine: AsyncEngine,
    stage: str,
) -> None:
    suffix = uuid4().hex
    raw_key = f"sk-gw-cancel-{suffix}"
    initial_balance = Decimal("10.00000000")
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=test_engine.url.render_as_string(hide_password=False),
        jwt_secret="gateway-cancellation-jwt-secret",
        encryption_key=Fernet.generate_key().decode(),
    )
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as setup:
        user = User(
            email=f"cancel-{suffix}@example.com",
            password_hash="unused",
            account=Account(balance=initial_balance),
        )
        user.api_keys.append(
            ApiKey(
                name="cancel",
                key_prefix=raw_key[:12],
                key_hash=sha256(raw_key.encode()).digest(),
                scope=ApiKeyScope.ALL,
            )
        )
        model = Model(
            canonical_name=f"cancel-model-{suffix}",
            display_name="Cancel Model",
            input_price_per_million=Decimal("1000"),
            output_price_per_million=Decimal("1000"),
        )
        alias = ModelAlias(alias=f"cancel-alias-{suffix}")
        model.aliases.append(alias)
        provider = Provider(
            name=f"cancel-provider-{suffix}",
            credential_encrypted=encrypt_secret(
                orjson.dumps({"api_key": "provider-secret"}).decode(),
                settings=settings,
            ),
        )
        provider_protocol = ProviderProtocol(
            protocol=Protocol.OPENAI,
            base_url="https://cancel-provider.example/v1",
        )
        provider.protocols.append(provider_protocol)
        setup.add_all((user, model, provider))
        await setup.flush()
        model_route = ModelRoute(
            model_id=model.id,
            provider_id=provider.id,
            upstream_model="cancel-native",
            weight=100,
        )
        setup.add(model_route)
        await setup.commit()
        user_id = user.id
        account_id = user.account.id
        alias_name = alias.alias
        route = RouteCandidate(
            route_id=model_route.id,
            model_id=model.id,
            provider_id=provider.id,
            provider_protocol_id=provider_protocol.id,
            protocol=Protocol.OPENAI,
            base_url=provider_protocol.base_url,
            websocket_url=None,
            upstream_model=model_route.upstream_model,
            weight=model_route.weight,
            provider_credential_encrypted=provider.credential_encrypted,
        )

    async def handler(request: httpx.Request) -> httpx.Response:
        if stage == "upstream_send":
            raise asyncio.CancelledError
        if stage in {"route_selection", "task_cancel_route_selection"}:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_cancel",
                "object": "chat.completion",
                "model": "cancel-native",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "completed"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    actual_billing = BillingService(session_factory)
    actual_audit = AuditService(session_factory)
    async with session_factory() as gateway_session:
        stage_router = StageRouter(route, stage)
        stage_billing = StageBilling(actual_billing, stage)
        service = GatewayService(
            session=gateway_session,
            settings=settings,
            billing_service=stage_billing,  # type: ignore[arg-type]
            audit_service=StageAudit(actual_audit, stage),  # type: ignore[arg-type]
            http_client_factory=FakeHttpClients(upstream_client),
            router_factory=lambda _: stage_router,
        )
        if stage == "task_cancel_route_selection":
            task = asyncio.create_task(
                service.handle(gateway_request(raw_key, alias_name), Protocol.OPENAI)
            )
            await stage_router.entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(asyncio.CancelledError) as cancellation:
                await service.handle(gateway_request(raw_key, alias_name), Protocol.OPENAI)
            if stage == "settlement_post_commit":
                assert cancellation.value is stage_billing.post_commit_cancellation
    await upstream_client.aclose()

    async with session_factory() as verify:
        account = await verify.get(Account, account_id)
        entries = (
            await verify.scalars(
                select(LedgerEntry)
                .where(LedgerEntry.account_id == account_id)
                .order_by(LedgerEntry.id)
            )
        ).all()
        audit = await verify.scalar(select(RequestLog).where(RequestLog.user_id == user_id))
        assert account is not None
        assert audit is not None
        assert audit.status is RequestStatus.CLIENT_DISCONNECTED
        assert {entry.kind for entry in entries} == {
            LedgerKind.RESERVATION,
            LedgerKind.RESERVATION_RELEASE,
            LedgerKind.USAGE,
        }
        assert len(entries) == 3
        if stage not in {"settlement", "audit_completion", "settlement_post_commit"}:
            assert account.balance == initial_balance
            assert entries[-1].amount == Decimal("0E-8")
        else:
            assert account.balance < initial_balance
            assert audit.prompt_tokens == 2
            assert audit.completion_tokens == 1
            assert audit.cost == Decimal("0.00300000")
