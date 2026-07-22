import logging
from collections.abc import AsyncIterator, Callable
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.enums import Protocol
from ai_gateway.db.session import get_session
from ai_gateway.gateway import models as models_module
from ai_gateway.gateway.dependencies import get_gateway_service
from ai_gateway.main import create_app


class FailingGatewayService:
    def __init__(self, exception: BaseException) -> None:
        self.exception = exception

    async def handle(self, *_: object, **__: object) -> None:
        raise self.exception


def _database_error() -> BaseException:
    return SQLAlchemyError("mysql+asyncmy://user:password@database/gateway")


def _timeout_error() -> BaseException:
    return TimeoutError("provider token secret timed out")


def _unexpected_error() -> BaseException:
    return RuntimeError("request body and encrypted value must not leak")


ERROR_CASES: tuple[tuple[Callable[[], BaseException], int, str, str], ...] = (
    (_database_error, 503, "database_unavailable", "Database unavailable"),
    (_timeout_error, 504, "timeout", "Request timed out"),
    (_unexpected_error, 500, "internal_error", "Internal server error"),
)


def _assert_native_error(
    protocol: Protocol,
    payload: dict[str, object],
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str,
) -> None:
    if protocol is Protocol.OPENAI:
        error = cast(dict[str, object], payload["error"])
        assert error == {
            "message": message,
            "type": "server_error",
            "code": code,
            "request_id": request_id,
        }
    elif protocol is Protocol.CLAUDE:
        assert payload == {
            "type": "error",
            "error": {"type": code, "message": message},
            "request_id": request_id,
        }
    else:
        error = cast(dict[str, object], payload["error"])
        assert error["code"] == status_code
        assert error["message"] == message
        assert error["request_id"] == request_id
        assert error["status"] == (
            "UNAVAILABLE"
            if status_code == 503
            else ("DEADLINE_EXCEEDED" if status_code == 504 else "INTERNAL")
        )


@pytest.mark.parametrize(
    ("protocol", "path", "body"),
    [
        (Protocol.OPENAI, "/v1/chat/completions", {"model": "test"}),
        (Protocol.CLAUDE, "/v1/messages", {"model": "test"}),
        (Protocol.GEMINI, "/v1beta/models/test:generateContent", {"contents": []}),
    ],
)
@pytest.mark.parametrize(("exception_factory", "status_code", "code", "message"), ERROR_CASES)
async def test_gateway_routes_use_safe_native_runtime_errors(
    protocol: Protocol,
    path: str,
    body: dict[str, object],
    exception_factory: Callable[[], BaseException],
    status_code: int,
    code: str,
    message: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app()
    app.dependency_overrides[get_gateway_service] = lambda: FailingGatewayService(
        exception_factory()
    )
    error_logger = logging.getLogger("ai_gateway.gateway.service")
    error_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger="ai_gateway.gateway.service"):
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                response = await client.post(path, json=body)
    finally:
        error_logger.removeHandler(caplog.handler)

    assert response.status_code == status_code
    request_id = response.headers["x-request-id"]
    assert str(UUID(request_id)) == request_id
    _assert_native_error(
        protocol,
        response.json(),
        status_code=status_code,
        code=code,
        message=message,
        request_id=request_id,
    )
    record = caplog.records[-1]
    assert record.exc_info is not None
    assert getattr(record, "request_id") == request_id
    assert "password" not in response.text
    assert "provider token" not in response.text
    assert "request body" not in response.text


@pytest.mark.parametrize(
    ("protocol", "path"),
    [
        (Protocol.OPENAI, "/v1/models"),
        (Protocol.OPENAI, "/v1/models/test-model"),
        (Protocol.GEMINI, "/v1beta/models"),
    ],
)
@pytest.mark.parametrize(("exception_factory", "status_code", "code", "message"), ERROR_CASES)
async def test_model_routes_use_safe_native_runtime_errors(
    protocol: Protocol,
    path: str,
    exception_factory: Callable[[], BaseException],
    status_code: int,
    code: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app: FastAPI = create_app()

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, object())

    async def fail_authentication(*_: object, **__: object) -> None:
        raise exception_factory()

    app.dependency_overrides[get_session] = session_override
    monkeypatch.setattr(models_module, "authenticate_api_key", fail_authentication)
    error_logger = logging.getLogger("ai_gateway.gateway.service")
    error_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger="ai_gateway.gateway.service"):
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
                headers={"authorization": "Bearer sk-gw-safe-test-placeholder"},
            ) as client:
                response = await client.get(path)
    finally:
        error_logger.removeHandler(caplog.handler)

    assert response.status_code == status_code
    request_id = response.headers["x-request-id"]
    assert str(UUID(request_id)) == request_id
    _assert_native_error(
        protocol,
        response.json(),
        status_code=status_code,
        code=code,
        message=message,
        request_id=request_id,
    )
    record = caplog.records[-1]
    assert record.exc_info is not None
    assert getattr(record, "request_id") == request_id
