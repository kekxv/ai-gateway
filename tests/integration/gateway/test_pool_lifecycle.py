from __future__ import annotations

import random
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

import httpx
import orjson
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from ai_gateway.audit.service import AuditService, RequestContext, RequestFailure, RequestResult
from ai_gateway.billing.service import BillingService
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import ApiKeyScope, Protocol, RequestStatus
from ai_gateway.core.security import encrypt_secret
from ai_gateway.db.models import (
    Account,
    ApiKey,
    Model,
    ModelRoute,
    Provider,
    ProviderProtocol,
    RequestLog,
    User,
)
from ai_gateway.gateway.dependencies import get_gateway_service
from ai_gateway.gateway.openai import router as openai_router
from ai_gateway.gateway.service import GatewayService
from ai_gateway.routing.service import Router


class _FakeAudit:
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


class _FakeHttpClients:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def client_for(self, _: str | httpx.URL) -> httpx.AsyncClient:
        return self._client


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], before_chunk: Callable[[int], None]) -> None:
        self._chunks = chunks
        self._before_chunk = before_chunk

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index, chunk in enumerate(self._chunks):
            self._before_chunk(index)
            yield chunk


@pytest.mark.parametrize("stream", [False, True])
async def test_gateway_request_does_not_self_exhaust_pool_size_one(
    test_engine: AsyncEngine,
    stream: bool,
) -> None:
    database_url = test_engine.url.render_as_string(hide_password=False)
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.1,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    raw_key = f"sk-gw-pool-{suffix}"
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        jwt_secret="pool-lifecycle-jwt-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )
    async with sessions() as setup:
        user = User(
            email=f"pool-{suffix}@example.com",
            password_hash="unused",
            account=Account(balance=Decimal("10.00000000")),
        )
        user.api_keys.append(
            ApiKey(
                name="pool lifecycle",
                key_prefix=raw_key[:12],
                key_hash=sha256(raw_key.encode()).digest(),
                scope=ApiKeyScope.ALL,
            )
        )
        model = Model(
            canonical_name=f"pool-model-{suffix}",
            display_name="Pool lifecycle",
            input_price_per_million=Decimal("1.00000000"),
            output_price_per_million=Decimal("1.00000000"),
        )
        provider = Provider(
            name=f"pool-provider-{suffix}",
            credential_encrypted=encrypt_secret(
                orjson.dumps({"api_key": "upstream-secret"}).decode(),
                settings=settings,
            ),
        )
        provider.protocols.append(
            ProviderProtocol(
                protocol=Protocol.OPENAI,
                base_url="https://pool-upstream.invalid/v1",
            )
        )
        route = ModelRoute(
            model=model,
            provider=provider,
            upstream_model="pool-native",
        )
        setup.add_all((user, route))
        await setup.commit()

    async def upstream_handler(_: httpx.Request) -> httpx.Response:
        if stream:
            events = [
                {
                    "id": "chatcmpl_pool",
                    "object": "chat.completion.chunk",
                    "model": "pool-native",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": "ok"},
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    "id": "chatcmpl_pool",
                    "object": "chat.completion.chunk",
                    "model": "pool-native",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 1},
                },
            ]
            chunks = [b"data: " + orjson.dumps(event) + b"\n\n" for event in events]
            chunks.append(b"data: [DONE]\n\n")
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_ChunkStream(
                    chunks,
                    lambda index: None if index < 2 else _assert_no_checked_out_connections(engine),
                ),
            )
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_pool",
                "object": "chat.completion",
                "model": "pool-native",
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

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    audit = _FakeAudit()
    try:
        async with sessions() as gateway_session:
            service = GatewayService(
                session=gateway_session,
                settings=settings,
                billing_service=BillingService(sessions),
                audit_service=audit,  # type: ignore[arg-type]
                http_client_factory=_FakeHttpClients(upstream_client),
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
                        "model": model.canonical_name,
                        "messages": [{"role": "user", "content": "hello"}],
                        "max_tokens": 8,
                        "stream": stream,
                    },
                )
    finally:
        await upstream_client.aclose()
        await engine.dispose()

    assert response.status_code == 200, response.text
    assert audit.completed is not None
    assert audit.failed is None


async def test_no_route_audit_does_not_self_exhaust_pool_size_one(
    test_engine: AsyncEngine,
) -> None:
    database_url = test_engine.url.render_as_string(hide_password=False)
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.1,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    raw_key = f"sk-gw-no-route-pool-{suffix}"
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        jwt_secret="no-route-pool-jwt-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
    )
    async with sessions() as setup:
        user = User(email=f"no-route-pool-{suffix}@example.com", password_hash="unused")
        user.api_keys.append(
            ApiKey(
                name="no route pool lifecycle",
                key_prefix=raw_key[:12],
                key_hash=sha256(raw_key.encode()).digest(),
                scope=ApiKeyScope.ALL,
            )
        )
        model = Model(
            canonical_name=f"no-route-pool-model-{suffix}",
            display_name="No route pool lifecycle",
        )
        setup.add_all((user, model))
        await setup.commit()

    async def unexpected_upstream(_: httpx.Request) -> httpx.Response:
        raise AssertionError("a request without an eligible route must not call upstream")

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(unexpected_upstream))
    try:
        async with sessions() as gateway_session:
            service = GatewayService(
                session=gateway_session,
                settings=settings,
                billing_service=BillingService(sessions),
                audit_service=AuditService(sessions),
                http_client_factory=_FakeHttpClients(upstream_client),
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
                        "model": model.canonical_name,
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                )

        async with sessions() as verify:
            request_log = await verify.scalar(
                select(RequestLog)
                .where(RequestLog.user_id == user.id)
                .order_by(RequestLog.created_at.desc())
            )
    finally:
        await upstream_client.aclose()
        await engine.dispose()

    assert response.status_code == 503, response.text
    assert request_log is not None
    assert request_log.status is RequestStatus.FAILED
    assert request_log.error_code == "no_route_available"
    assert request_log.model_id == model.id


def _assert_no_checked_out_connections(engine: AsyncEngine) -> None:
    checked_out = engine.sync_engine.pool.checkedout()  # type: ignore[attr-defined]
    assert checked_out == 0, "request session held a connection across upstream SSE I/O"
