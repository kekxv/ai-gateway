from __future__ import annotations

import gzip
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy import delete, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ai_gateway.audit.codec import gunzip_json, gzip_json
from ai_gateway.audit.service import (
    AuditService,
    RequestContext,
    RequestFailure,
    RequestResult,
)
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.enums import Protocol, RequestStatus, UsageSource
from ai_gateway.core.security import hash_password, issue_access_token
from ai_gateway.db.models import (
    Account,
    ApiKey,
    Model,
    ModelRoute,
    Provider,
    ProviderProtocol,
    RequestLog,
    RequestLogDetail,
    User,
)
from ai_gateway.db.session import get_session
from ai_gateway.main import create_app


@pytest.fixture
def audit_session_factory(
    session: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    assert session.bind is not None
    return async_sessionmaker(
        bind=session.bind,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest_asyncio.fixture
async def audit_records(
    session: AsyncSession,
) -> tuple[User, User, ApiKey, Model, Provider, ModelRoute]:
    admin = User(
        email="audit-admin@example.com",
        password_hash=hash_password("audit-admin-password"),
        role="admin",
    )
    admin.account = Account()
    member = User(
        email="audit-member@example.com",
        password_hash=hash_password("audit-member-password"),
        role="user",
    )
    member.account = Account()
    session.add_all([admin, member])
    await session.flush()

    api_key = ApiKey(
        user_id=member.id,
        name="audit-key",
        key_prefix="sk-gw-audit-",
        key_hash=sha256(b"sk-gw-audit-key").digest(),
    )
    provider = Provider(
        name="audit-provider",
        credential_encrypted=b"encrypted",
    )
    model = Model(
        canonical_name="audit-model",
        display_name="Audit Model",
    )
    session.add_all([api_key, provider, model])
    await session.flush()

    provider_protocol = ProviderProtocol(
        provider_id=provider.id,
        protocol=Protocol.CLAUDE,
        base_url="https://provider.invalid",
    )
    session.add(provider_protocol)
    await session.flush()
    route = ModelRoute(
        model_id=model.id,
        provider_id=provider.id,
        upstream_model="provider-audit-model",
    )
    session.add(route)
    await session.flush()
    return admin, member, api_key, model, provider, route


@pytest.fixture
def audit_settings() -> Settings:
    return Settings(
        environment="test",
        jwt_secret="audit-integration-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
        audit_body_limit_bytes=4096,
    )


async def _client_for(
    session: AsyncSession,
    settings: Settings,
    user: User,
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    token = issue_access_token(user_id=user.id, settings=settings)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client


async def test_request_lifecycle_writes_started_completion_and_redacted_details(
    session: AsyncSession,
    audit_session_factory: async_sessionmaker[AsyncSession],
    audit_records: tuple[User, User, ApiKey, Model, Provider, ModelRoute],
    audit_settings: Settings,
) -> None:
    _, member, api_key, model, provider, route = audit_records
    service = AuditService(
        audit_session_factory,
        body_limit_bytes=audit_settings.audit_body_limit_bytes,
    )
    context = RequestContext(
        user_id=member.id,
        api_key_id=api_key.id,
        model_id=model.id,
        inbound_protocol=Protocol.OPENAI,
        transport="http",
        stream=False,
        headers={
            "Authorization": "Bearer must-not-be-stored",
            "X-Trace": "trace-123",
        },
    )
    request_body = (
        b'{"api_key":"must-not-be-stored","messages":'
        b'[{"role":"user","content":"keep this message"}]}'
    )

    request_id = await service.start_request(context, request_body)
    started = await session.get(RequestLog, str(request_id))
    started_detail = await session.get(RequestLogDetail, str(request_id))

    assert started is not None
    assert started.status is RequestStatus.STARTED
    assert started.provider_id is None
    assert started.completed_at is None
    assert started_detail is not None
    assert started_detail.request_detail_gzip is not None
    request_detail = gunzip_json(started_detail.request_detail_gzip)
    assert request_detail == {
        "body": {
            "api_key": "[REDACTED]",
            "messages": [{"content": "keep this message", "role": "user"}],
        },
        "headers": {"X-Trace": "trace-123"},
    }

    await service.complete_request(
        request_id,
        RequestResult(
            provider_id=provider.id,
            model_route_id=route.id,
            outbound_protocol=Protocol.CLAUDE,
            http_status=200,
            prompt_tokens=1250,
            completion_tokens=375,
            cache_read_tokens=1000,
            cache_write_tokens=250,
            usage_source=UsageSource.PROVIDER,
            cost=Decimal("0.00041250"),
            cost_amount=Decimal("0.00012375"),
            latency_ms=321,
            first_token_ms=87,
            headers={"Set-Cookie": "must-not-be-stored", "Content-Type": "application/json"},
            body=b'{"access_token":"must-not-be-stored","result":"ok"}',
        ),
    )
    await session.refresh(started)
    await session.refresh(started_detail)

    assert started.status is RequestStatus.COMPLETED
    assert started.provider_id == provider.id
    assert started.model_route_id == route.id
    assert started.outbound_protocol is Protocol.CLAUDE
    assert started.http_status == 200
    assert started.prompt_tokens == 1250
    assert started.completion_tokens == 375
    assert started.cache_read_tokens == 1000
    assert started.cache_write_tokens == 250
    assert started.usage_source is UsageSource.PROVIDER
    assert started.cost == Decimal("0.00041250")
    assert started.cost_amount == Decimal("0.00012375")
    assert started.latency_ms == 321
    assert started.first_token_ms == 87
    assert started.completed_at is not None
    assert started_detail.response_detail_gzip is not None
    assert gunzip_json(started_detail.response_detail_gzip) == {
        "body": {"access_token": "[REDACTED]", "result": "ok"},
        "headers": {"Content-Type": "application/json"},
        "usage": {
            "input_tokens": 1250,
            "output_tokens": 375,
            "cache_read_tokens": 1000,
            "cache_write_tokens": 250,
            "source": "provider",
        },
    }


async def test_claude_sse_response_detail_is_structured_redacted_and_includes_usage(
    session: AsyncSession,
    audit_session_factory: async_sessionmaker[AsyncSession],
    audit_records: tuple[User, User, ApiKey, Model, Provider, ModelRoute],
) -> None:
    _, member, api_key, model, provider, route = audit_records
    service = AuditService(audit_session_factory)
    request_id = await service.start_request(
        RequestContext(
            user_id=member.id,
            api_key_id=api_key.id,
            model_id=model.id,
            inbound_protocol=Protocol.CLAUDE,
            transport="http",
            stream=True,
        ),
        b"{}",
    )
    sse_body = (
        b"event: message_start\n"
        b'data: {"type":"message_start","message":{"type":"message",'
        b'"usage":{"input_tokens":32769,"cache_read_input_tokens":12000,'
        b'"cache_creation_input_tokens":8000}},"api_key":"stream-secret"}\n\n'
        b"event: content_block_delta\n"
        b'data: {"type":"content_block_delta","index":0,'
        b'"delta":{"type":"text_delta","text":"hello"}}\n\n'
        b"event: message_delta\n"
        b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},'
        b'"usage":{"output_tokens":517}}\n\n'
        b"event: message_stop\n"
        b'data: {"type":"message_stop"}\n\n'
    )

    await service.complete_request(
        request_id,
        RequestResult(
            provider_id=provider.id,
            model_route_id=route.id,
            outbound_protocol=Protocol.CLAUDE,
            http_status=200,
            prompt_tokens=32769,
            completion_tokens=517,
            cache_read_tokens=12000,
            cache_write_tokens=8000,
            usage_source=UsageSource.PROVIDER,
            headers={"Content-Type": "text/event-stream;charset=UTF-8"},
            body=sse_body,
        ),
    )
    stored_detail = await session.get(RequestLogDetail, str(request_id))

    assert stored_detail is not None
    assert stored_detail.response_detail_gzip is not None
    detail = gunzip_json(stored_detail.response_detail_gzip)
    assert detail["body"]["format"] == "sse"
    assert detail["body"]["byte_length"] == len(sse_body)
    assert detail["body"]["event_count"] == 4
    assert detail["body"]["events"][0]["event"] == "message_start"
    assert detail["body"]["events"][0]["data"]["type"] == "message_start"
    assert detail["body"]["events"][0]["data"]["api_key"] == "[REDACTED]"
    assert detail["body"]["events"][1]["data"]["delta"]["text"] == "hello"
    assert detail["usage"] == {
        "input_tokens": 32769,
        "output_tokens": 517,
        "cache_read_tokens": 12000,
        "cache_write_tokens": 8000,
        "source": "provider",
    }


@pytest.mark.parametrize(
    ("client_disconnected", "expected_status"),
    [(False, RequestStatus.FAILED), (True, RequestStatus.CLIENT_DISCONNECTED)],
)
async def test_failure_lifecycle_distinguishes_upstream_error_and_disconnect(
    client_disconnected: bool,
    expected_status: RequestStatus,
    session: AsyncSession,
    audit_session_factory: async_sessionmaker[AsyncSession],
    audit_records: tuple[User, User, ApiKey, Model, Provider, ModelRoute],
) -> None:
    _, member, api_key, model, provider, route = audit_records
    service = AuditService(audit_session_factory)
    request_id = await service.start_request(
        RequestContext(
            user_id=member.id,
            api_key_id=api_key.id,
            model_id=model.id,
            inbound_protocol=Protocol.GEMINI,
            transport="http",
            stream=True,
        ),
        b"{}",
    )

    await service.fail_request(
        request_id,
        RequestFailure(
            error_code="upstream_timeout",
            client_disconnected=client_disconnected,
            provider_id=provider.id,
            model_route_id=route.id,
            outbound_protocol=Protocol.CLAUDE,
            http_status=504,
            latency_ms=900,
            first_token_ms=120,
            body={"password": "must-not-be-stored", "attempt": 2},
        ),
    )
    stored = await session.get(RequestLog, str(request_id))
    stored_detail = await session.get(RequestLogDetail, str(request_id))

    assert stored is not None
    assert stored.status is expected_status
    assert stored.error_code == "upstream_timeout"
    assert stored.completed_at is not None
    assert stored_detail is not None
    assert stored_detail.response_detail_gzip is not None
    assert gunzip_json(stored_detail.response_detail_gzip)["body"]["password"] == "[REDACTED]"


async def test_audit_write_failure_is_logged_and_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BrokenSessionContext:
        async def __aenter__(self) -> AsyncSession:
            raise RuntimeError(
                "password=log-secret SQL params={'access_token': 'sql-param-secret'}"
            )

        async def __aexit__(self, *_: object) -> None:
            return None

    service = AuditService(lambda: BrokenSessionContext())
    context = RequestContext(
        user_id=1,
        inbound_protocol=Protocol.OPENAI,
        transport="http",
        stream=False,
    )

    with caplog.at_level(logging.ERROR, logger="ai_gateway.audit.service"):
        request_id = await service.start_request(context, b'{"password":"never logged"}')
        await service.complete_request(request_id, RequestResult(http_status=200))
        await service.fail_request(request_id, RequestFailure(error_code="upstream_error"))

    assert request_id.version == 4
    assert caplog.text.count("Audit write failed") == 3
    assert "never logged" not in caplog.text
    assert "log-secret" not in caplog.text
    assert "sql-param-secret" not in caplog.text
    assert "RuntimeError" in caplog.text


async def test_default_lifecycle_wrappers_do_not_raise_when_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import ai_gateway.audit.service as audit_service

    def fail_setup() -> AuditService:
        raise RuntimeError("Authorization=Bearer wrapper-log-secret")

    monkeypatch.setattr(audit_service, "_default_service", fail_setup)
    context = RequestContext(
        user_id=1,
        inbound_protocol=Protocol.OPENAI,
        transport="http",
        stream=False,
    )
    with caplog.at_level(logging.ERROR, logger="ai_gateway.audit.service"):
        request_id = await audit_service.start_request(context, b"{}")
        await audit_service.complete_request(request_id, RequestResult(http_status=200))
        await audit_service.fail_request(
            request_id,
            RequestFailure(error_code="upstream_error"),
        )

    assert request_id.version == 4
    assert caplog.text.count("Audit write failed") == 3
    assert "wrapper-log-secret" not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.parametrize(
    ("body", "secret"),
    [
        (b'{"password":"invalid-utf8-secret-\xff"}', b"invalid-utf8-secret"),
        (b'{"access_token":"incomplete-json-secret"', b"incomplete-json-secret"),
    ],
)
async def test_unparseable_request_bodies_store_only_safe_metadata(
    body: bytes,
    secret: bytes,
    caplog: pytest.LogCaptureFixture,
    session: AsyncSession,
    audit_session_factory: async_sessionmaker[AsyncSession],
    audit_records: tuple[User, User, ApiKey, Model, Provider, ModelRoute],
) -> None:
    _, member, api_key, model, _, _ = audit_records
    service = AuditService(audit_session_factory)

    request_id = await service.start_request(
        RequestContext(
            user_id=member.id,
            api_key_id=api_key.id,
            model_id=model.id,
            inbound_protocol=Protocol.OPENAI,
            transport="http",
            stream=False,
        ),
        body,
    )
    stored = await session.get(RequestLog, str(request_id))
    stored_detail = await session.get(RequestLogDetail, str(request_id))

    assert stored is not None
    assert stored_detail is not None
    assert stored_detail.request_detail_gzip is not None
    uncompressed = gzip.decompress(stored_detail.request_detail_gzip)
    detail = gunzip_json(stored_detail.request_detail_gzip)
    assert detail["body"]["unparseable"] is True
    assert detail["body"]["byte_length"] == len(body)
    assert "sha256" in detail["body"]
    assert secret not in stored_detail.request_detail_gzip
    assert secret not in uncompressed
    assert secret.decode() not in str(detail)
    assert secret.decode() not in caplog.text


async def test_dataclass_and_pydantic_bodies_are_normalized_then_redacted(
    caplog: pytest.LogCaptureFixture,
    session: AsyncSession,
    audit_session_factory: async_sessionmaker[AsyncSession],
    audit_records: tuple[User, User, ApiKey, Model, Provider, ModelRoute],
) -> None:
    @dataclass
    class CredentialRecord:
        credential: str
        safe: str

    class NestedPayload(BaseModel):
        access_token: str
        records: list[CredentialRecord]

    _, member, api_key, model, _, _ = audit_records
    service = AuditService(audit_session_factory)
    request_id = await service.start_request(
        RequestContext(
            user_id=member.id,
            api_key_id=api_key.id,
            model_id=model.id,
            inbound_protocol=Protocol.OPENAI,
            transport="http",
            stream=False,
        ),
        b"{}",
    )
    body = {
        "password": "mapping-secret",
        "nested": NestedPayload(
            access_token="pydantic-secret",
            records=[CredentialRecord(credential="dataclass-secret", safe="preserved")],
        ),
    }

    await service.complete_request(request_id, RequestResult(http_status=200, body=body))
    stored = await session.get(RequestLog, str(request_id))
    stored_detail = await session.get(RequestLogDetail, str(request_id))

    assert stored is not None
    assert stored_detail is not None
    assert stored_detail.response_detail_gzip is not None
    uncompressed = gzip.decompress(stored_detail.response_detail_gzip)
    detail = gunzip_json(stored_detail.response_detail_gzip)
    assert detail["body"] == {
        "password": "[REDACTED]",
        "nested": {
            "access_token": "[REDACTED]",
            "records": [{"credential": "[REDACTED]", "safe": "preserved"}],
        },
    }
    for secret in (b"mapping-secret", b"pydantic-secret", b"dataclass-secret"):
        assert secret not in stored_detail.response_detail_gzip
        assert secret not in uncompressed
        assert secret.decode() not in caplog.text


async def test_custom_app_binds_module_audit_lifecycle_to_its_own_configuration(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    test_engine: AsyncEngine,
) -> None:
    del test_engine
    import ai_gateway.audit.service as audit_service

    database_url = os.environ["GATEWAY_TEST_DATABASE_URL"]
    settings = Settings(
        environment="test",
        database_url=database_url,
        jwt_secret="app-scoped-audit-secret-at-least-32-bytes",
        encryption_key=Fernet.generate_key().decode(),
        audit_body_limit_bytes=64,
    )
    app: FastAPI = create_app(settings)
    session_factory = app.state.session_factory
    async with session_factory() as seed_session:
        user = User(
            email=f"app-audit-{datetime.now(UTC).timestamp()}@example.com",
            password_hash=hash_password("app-audit-password"),
            role="user",
        )
        user.account = Account()
        seed_session.add(user)
        await seed_session.commit()
        await seed_session.refresh(user)
        user_id = user.id

    def fail_global_service() -> AuditService:
        raise RuntimeError("global-resource-secret")

    monkeypatch.setattr(audit_service, "_default_service", fail_global_service)

    @app.post("/_test/app-audit")
    async def app_audit() -> dict[str, str]:
        request_id = await audit_service.start_request(
            RequestContext(
                user_id=user_id,
                inbound_protocol=Protocol.OPENAI,
                transport="http",
                stream=False,
            ),
            b'{"message":"request body large enough to exceed the custom app limit"}',
        )
        await audit_service.complete_request(
            request_id,
            RequestResult(
                http_status=200,
                body={"message": "response body large enough to exceed the custom app limit"},
            ),
        )
        return {"id": str(request_id)}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/_test/app-audit")

    with caplog.at_level(logging.ERROR, logger="ai_gateway.audit.service"):
        outside_request_id = await audit_service.start_request(
            RequestContext(
                user_id=user_id,
                inbound_protocol=Protocol.OPENAI,
                transport="http",
                stream=False,
            ),
            b"{}",
        )

    assert response.status_code == 200, response.text
    request_id = response.json()["id"]
    async with session_factory() as check_session:
        stored = await check_session.get(RequestLog, request_id)
        stored_detail = await check_session.get(RequestLogDetail, str(request_id))
        assert stored is not None
        assert stored_detail is not None
        assert stored_detail.request_detail_gzip is not None
        assert stored_detail.response_detail_gzip is not None
        assert gunzip_json(stored_detail.request_detail_gzip)["truncated"] is True
        assert gunzip_json(stored_detail.response_detail_gzip)["truncated"] is True
        assert await check_session.get(RequestLog, str(outside_request_id)) is None
        await check_session.execute(delete(RequestLog).where(RequestLog.id == request_id))
        await check_session.execute(delete(Account).where(Account.user_id == user_id))
        await check_session.execute(delete(User).where(User.id == user_id))
        await check_session.commit()
    await app.state.engine.dispose()
    assert "global-resource-secret" not in caplog.text


async def test_admin_list_filters_cursor_and_detail_are_safe(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncSession,
    audit_session_factory: async_sessionmaker[AsyncSession],
    audit_records: tuple[User, User, ApiKey, Model, Provider, ModelRoute],
    audit_settings: Settings,
) -> None:
    admin, member, api_key, model, provider, route = audit_records
    service = AuditService(audit_session_factory)
    ids = []
    for index, protocol in enumerate((Protocol.OPENAI, Protocol.CLAUDE, Protocol.GEMINI)):
        request_id = await service.start_request(
            RequestContext(
                user_id=member.id,
                api_key_id=api_key.id,
                model_id=model.id,
                inbound_protocol=protocol,
                transport="http",
                stream=False,
            ),
            b'{"credential":"must-not-be-stored","message":"safe"}',
        )
        await service.complete_request(
            request_id,
            RequestResult(
                provider_id=provider.id,
                model_route_id=route.id,
                outbound_protocol=Protocol.CLAUDE,
                http_status=200 + index,
                cost=Decimal("0.00000001"),
                cost_amount=Decimal("0.000000005"),
                body={"secret": "must-not-be-stored", "index": index},
            ),
        )
        ids.append(request_id)

    async for client in _client_for(session, audit_settings, admin):
        import ai_gateway.admin.request_logs as request_logs_api

        def fail_if_decompressed(_: bytes) -> dict[str, object]:
            raise AssertionError("list endpoint must never decompress detail blobs")

        monkeypatch.setattr(request_logs_api, "gunzip_json", fail_if_decompressed)
        statements: list[str] = []

        def capture_statement(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            statements.append(statement)

        assert session.bind is not None
        sync_engine = session.bind.engine.sync_engine
        event.listen(sync_engine, "before_cursor_execute", capture_statement)
        try:
            first = await client.get("/admin/request-logs", params={"page_size": 2})
        finally:
            event.remove(sync_engine, "before_cursor_execute", capture_statement)
        assert first.status_code == 200, first.text
        list_selects = [
            statement
            for statement in statements
            if "SELECT" in statement.upper() and "request_logs" in statement
        ]
        assert list_selects
        assert all("request_detail_gzip" not in statement for statement in list_selects)
        assert all("response_detail_gzip" not in statement for statement in list_selects)
        first_body = first.json()
        assert len(first_body["items"]) == 2
        assert first_body["next_cursor"] is not None
        assert all("request_detail" not in item for item in first_body["items"])
        assert all("response_detail" not in item for item in first_body["items"])
        assert all("cache_read_tokens" in item for item in first_body["items"])
        assert all("cache_write_tokens" in item for item in first_body["items"])
        assert all(
            Decimal(item["cost_amount"]) == Decimal("0.00000001") for item in first_body["items"]
        )
        for item in first_body["items"]:
            assert item["user_email"] == "audit-member@example.com"
            assert item["api_key_name"] == "audit-key"
            assert item["api_key_prefix"] == "sk-gw-audit-"
            assert item["model_name"] == "audit-model"
            assert item["provider_name"] == "audit-provider"
            assert item["route_upstream_model"] == "provider-audit-model"

        second = await client.get(
            "/admin/request-logs",
            params={"page_size": 2, "cursor": first_body["next_cursor"]},
        )
        second_body = second.json()
        listed_ids = [item["id"] for item in first_body["items"] + second_body["items"]]
        assert len(listed_ids) == len(set(listed_ids)) == 3

        filtered = await client.get(
            "/admin/request-logs",
            params={
                "request_id": str(ids[0]),
                "user_id": member.id,
                "api_key_id": api_key.id,
                "model_id": model.id,
                "provider_id": provider.id,
                "status": "completed",
                "protocol": "openai",
                "created_from": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "created_to": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            },
        )
        assert filtered.status_code == 200, filtered.text
        assert [item["id"] for item in filtered.json()["items"]] == [str(ids[0])]

        too_large = await client.get("/admin/request-logs", params={"page_size": 201})
        assert too_large.status_code == 422
        invalid_cursor = await client.get("/admin/request-logs", params={"cursor": "***"})
        assert invalid_cursor.status_code == 422
        assert invalid_cursor.json()["detail"]["code"] == "invalid_cursor"

        monkeypatch.undo()
        detail = await client.get(f"/admin/request-logs/{ids[0]}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["user_email"] == "audit-member@example.com"
        assert detail.json()["api_key_name"] == "audit-key"
        assert detail.json()["api_key_prefix"] == "sk-gw-audit-"
        assert detail.json()["model_name"] == "audit-model"
        assert detail.json()["provider_name"] == "audit-provider"
        assert detail.json()["route_upstream_model"] == "provider-audit-model"
        assert Decimal(detail.json()["cost_amount"]) == Decimal("0.00000001")
        assert detail.json()["request_detail"]["body"]["credential"] == "[REDACTED]"
        assert detail.json()["response_detail"]["body"]["secret"] == "[REDACTED]"


async def test_user_list_and_detail_include_readable_catalog_identities(
    session: AsyncSession,
    audit_session_factory: async_sessionmaker[AsyncSession],
    audit_records: tuple[User, User, ApiKey, Model, Provider, ModelRoute],
    audit_settings: Settings,
) -> None:
    _, member, api_key, model, provider, route = audit_records
    service = AuditService(audit_session_factory)
    request_id = await service.start_request(
        RequestContext(
            user_id=member.id,
            api_key_id=api_key.id,
            model_id=model.id,
            inbound_protocol=Protocol.CLAUDE,
            transport="http",
            stream=True,
        ),
        b"{}",
    )
    await service.complete_request(
        request_id,
        RequestResult(
            provider_id=provider.id,
            model_route_id=route.id,
            outbound_protocol=Protocol.CLAUDE,
            http_status=200,
            cost=Decimal("0.00000002"),
            cost_amount=Decimal("0.00000001"),
        ),
    )

    async for client in _client_for(session, audit_settings, member):
        listing = await client.get(
            "/user/request-logs",
            params={"request_id": str(request_id)},
        )
        detail = await client.get(f"/user/request-logs/{request_id}")

    assert listing.status_code == 200, listing.text
    assert detail.status_code == 200, detail.text
    for item in (listing.json()["items"][0], detail.json()):
        assert "user_email" not in item
        assert item["api_key_name"] == "audit-key"
        assert item["api_key_prefix"] == "sk-gw-audit-"
        assert item["model_name"] == "audit-model"
        for hidden_field in (
            "provider_id",
            "provider_name",
            "model_route_id",
            "route_upstream_model",
            "cost_amount",
        ):
            assert hidden_field not in item


async def test_request_log_endpoints_require_admin(
    session: AsyncSession,
    audit_records: tuple[User, User, ApiKey, Model, Provider, ModelRoute],
    audit_settings: Settings,
) -> None:
    _, member, _, _, _, _ = audit_records
    async for client in _client_for(session, audit_settings, member):
        listing = await client.get("/admin/request-logs")
        detail = await client.get("/admin/request-logs/00000000-0000-0000-0000-000000000000")

    assert listing.status_code == 403
    assert detail.status_code == 403
    assert listing.json()["detail"]["code"] == "admin_required"


def test_stored_repetitive_fixture_is_smaller_than_uncompressed_json() -> None:
    value = {"body": {"message": "audit fixture " * 1000}}

    assert len(gzip_json(value)) < len(str(value).encode())
