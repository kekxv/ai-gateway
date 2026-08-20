from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from starlette.requests import ClientDisconnect

from ai_gateway.audit.service import RequestContext, RequestFailure, RequestResult
from ai_gateway.billing.service import BillingService
from ai_gateway.core.config import Settings
from ai_gateway.core.enums import LedgerKind, Protocol, RouteRuntimeState, UsageSource
from ai_gateway.db.models import Account, LedgerEntry, Model, User
from ai_gateway.gateway.service import GatewayService, GatewayStreamOutput, _StreamLifecycle
from ai_gateway.protocols.registry import get_adapter
from ai_gateway.routing.types import RouteCandidate
from ai_gateway.transport.sse import GatewayContext, stream_gateway_response


class DisconnectStream(httpx.AsyncByteStream):
    def __init__(self, chunks: Iterable[bytes], *, fail_after: int | None = None) -> None:
        self.chunks = tuple(chunks)
        self.fail_after = fail_after
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index, chunk in enumerate(self.chunks):
            if index == self.fail_after:
                raise httpx.ReadError("stream failed")
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class RecordingAudit:
    completed: RequestResult | None = None
    failed: RequestFailure | None = None
    complete_calls: int = 0
    fail_calls: int = 0

    async def start_request(
        self,
        _: RequestContext,
        __: bytes,
        *,
        request_id: UUID | None = None,
    ) -> UUID:
        return request_id or uuid4()

    async def complete_request(self, _: UUID, result: RequestResult) -> None:
        self.complete_calls += 1
        self.completed = result

    async def fail_request(self, _: UUID, failure: RequestFailure) -> None:
        self.fail_calls += 1
        self.failed = failure


@dataclass
class RecordingRouter:
    successes: list[int] = field(default_factory=list)
    failures: list[int] = field(default_factory=list)
    releases: list[int] = field(default_factory=list)
    consecutive_failures: int = 2
    runtime_state: RouteRuntimeState = RouteRuntimeState.HALF_OPEN

    async def record_success(self, route_id: int) -> bool:
        self.successes.append(route_id)
        self.consecutive_failures = 0
        self.runtime_state = RouteRuntimeState.CLOSED
        return True

    async def record_failure(self, route_id: int, _: object) -> bool:
        self.failures.append(route_id)
        self.consecutive_failures += 1
        return True

    async def release_half_open(self, route_id: int) -> bool:
        self.releases.append(route_id)
        self.runtime_state = RouteRuntimeState.OPEN
        return True


class UnusedHttpClients:
    async def client_for(
        self,
        _: str | httpx.URL,
        *,
        provider_id: int | None = None,
        proxy_config_encrypted: bytes | None = None,
    ) -> httpx.AsyncClient:
        raise AssertionError("direct stream lifecycle test must not send a request")


@pytest.mark.parametrize(
    "termination",
    (
        "unstarted_iterator",
        "response_start_failure",
        "immediate_disconnect",
        "disconnect",
        "read_error",
    ),
)
async def test_mysql_stream_termination_closes_upstream_and_settles_reservation(
    test_engine: AsyncEngine,
    termination: str,
) -> None:
    suffix = uuid4().hex
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as setup:
        user = User(email=f"stream-{suffix}@example.com", password_hash="unused")
        user.account = Account(balance=Decimal("1.00000000"))
        model = Model(
            canonical_name=f"stream-{suffix}",
            display_name="Stream Disconnect",
            input_price_per_million=Decimal("1.00000000"),
            output_price_per_million=Decimal("2.00000000"),
        )
        setup.add_all((user, model))
        await setup.commit()
        user_id = user.id

    billing = BillingService(session_factory)
    reservation = await billing.reserve_balance(
        user_id=user_id,
        model=model,
        estimated_input_tokens=2,
        max_output_tokens=8,
        idempotency_key=f"stream:{suffix}",
        request_id=uuid4(),
    )
    audit = RecordingAudit()
    router = RecordingRouter()
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=test_engine.url.render_as_string(hide_password=False),
        jwt_secret="stream-disconnect-jwt",
        encryption_key=Fernet.generate_key().decode(),
    )
    async with session_factory() as gateway_session:
        service = GatewayService(
            session=gateway_session,
            settings=settings,
            billing_service=billing,
            audit_service=audit,  # type: ignore[arg-type]
            http_client_factory=UnusedHttpClients(),
        )
        canonical_request = get_adapter(Protocol.OPENAI).decode_request(
            {
                "model": model.canonical_name,
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 8,
                "stream": True,
            }
        )
        first = b'data: {"model":"m","choices":[{"index":0,"delta":{"content":"hello"}}]}\n\n'
        terminal = (
            b'data: {"model":"m","choices":[],"usage":'
            b'{"prompt_tokens":2,"completion_tokens":1}}\n\n'
        )
        native_stream = DisconnectStream(
            (first, terminal, b"data: [DONE]\n\n"),
            fail_after=1 if termination == "read_error" else None,
        )
        upstream = httpx.Response(200, stream=native_stream)
        route = RouteCandidate(
            route_id=41,
            model_id=model.id,
            provider_id=42,
            provider_protocol_id=43,
            protocol=Protocol.OPENAI,
            base_url="https://provider.example/v1",
            websocket_url=None,
            upstream_model="m",
            weight=100,
            runtime_state=RouteRuntimeState.HALF_OPEN,
        )
        context = GatewayContext(
            Protocol.OPENAI,
            Protocol.OPENAI,
            initial_input_tokens=2,
        )
        source = stream_gateway_response(context, upstream)
        prefetched = await anext(source)
        lifecycle = _StreamLifecycle(
            service=service,
            context=context,
            upstream=upstream,
            source=source,
            prefetched_frame=prefetched,
            request=canonical_request,
            reservation=reservation,
            billing_key=f"stream:{suffix}",
            audit_id=uuid4(),
            route=route,
            attempts=({"attempt": 1, "route_id": route.route_id},),
            router=router,
            priced_model=model,
            provider=None,
            started_at=context.started_at,
        )
        body = lifecycle.iterator()

        if termination == "unstarted_iterator":
            await body.aclose()
        elif termination in {"response_start_failure", "immediate_disconnect"}:
            response = GatewayStreamOutput(lifecycle, 200).response()

            async def receive() -> dict[str, str]:
                return {"type": "http.disconnect"}

            async def send(_: object) -> None:
                if termination == "immediate_disconnect":
                    raise ClientDisconnect
                raise RuntimeError("response start failed")

            expected = ClientDisconnect if termination == "immediate_disconnect" else RuntimeError
            with pytest.raises(expected):
                await response(
                    {
                        "type": "http",
                        "asgi": {"version": "3.0", "spec_version": "2.4"},
                        "http_version": "1.1",
                        "method": "POST",
                        "scheme": "http",
                        "path": "/v1/chat/completions",
                        "raw_path": b"/v1/chat/completions",
                        "query_string": b"",
                        "root_path": "",
                        "headers": [],
                        "client": ("127.0.0.1", 1),
                        "server": ("test", 80),
                    },
                    receive,
                    send,
                )
        elif termination == "disconnect":
            assert await anext(body) == first
            await body.aclose()
        else:
            assert await anext(body) == first
            with pytest.raises(httpx.ReadError, match="stream failed"):
                await anext(body)

    async with session_factory() as verify:
        entries = tuple(
            await verify.scalars(
                select(LedgerEntry).where(LedgerEntry.request_id == reservation.request_id)
            )
        )

    assert native_stream.closed
    assert {entry.kind for entry in entries} == {
        LedgerKind.RESERVATION,
        LedgerKind.RESERVATION_RELEASE,
        LedgerKind.USAGE,
    }
    assert audit.completed is None
    assert audit.failed is not None
    assert audit.complete_calls == 0
    assert audit.fail_calls == 1
    assert audit.failed.client_disconnected == (
        termination in {"unstarted_iterator", "immediate_disconnect", "disconnect"}
    )
    assert audit.failed.usage_source is UsageSource.ESTIMATED
    assert audit.failed.prompt_tokens == 2
    assert audit.failed.completion_tokens > 0
    assert router.successes == []
    assert router.failures == ([route.route_id] if termination == "read_error" else [])
    if termination != "read_error":
        assert router.releases == [route.route_id]
        assert router.consecutive_failures == 2
        assert router.runtime_state is RouteRuntimeState.OPEN
    else:
        assert router.releases == []
