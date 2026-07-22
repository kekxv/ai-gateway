import json
import logging
from io import StringIO
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException, Query
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from ai_gateway.core.logging import JsonLogFormatter, current_request_id, log_context
from ai_gateway.main import create_app


async def test_request_id_is_validated_returned_and_bound_to_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app()

    @app.get("/_test/request-id")
    async def request_id_endpoint() -> dict[str, str]:
        logging.getLogger("ai_gateway.test").info("request handled")
        return {"status": "ok"}

    supplied = str(uuid4())
    application_logger = logging.getLogger("ai_gateway.test")
    application_logger.addHandler(caplog.handler)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with caplog.at_level(logging.INFO, logger="ai_gateway.test"):
                response = await client.get(
                    "/_test/request-id",
                    headers={"x-request-id": supplied},
                )
                application_log = json.loads(JsonLogFormatter().format(caplog.records[-1]))
            generated = (
                await client.get(
                    "/_test/request-id",
                    headers={"x-request-id": "not-a-uuid"},
                )
            ).headers["x-request-id"]
    finally:
        application_logger.removeHandler(caplog.handler)

    assert response.headers["x-request-id"] == supplied
    assert application_log["request_id"] == supplied
    assert str(UUID(generated)) == generated
    assert current_request_id() is None


def test_json_logs_are_structured_and_sensitive_values_are_redacted() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("ai_gateway.redaction-test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    with log_context(request_id=str(uuid4()), route_id=42):
        try:
            raise RuntimeError("stack-only database-password-must-not-leak")
        except RuntimeError:
            logger.exception(
                "authorization=Bearer bearer-secret "
                "api_key=provider-secret token=jwt.secret "
                "encrypted=fernet-ciphertext body={secret-prompt} "
                "provider=mysql+asyncmy://user:pass@example.test/gateway"
            )

    payload = json.loads(stream.getvalue())
    assert set(payload) == {
        "timestamp",
        "level",
        "logger",
        "event",
        "request_id",
        "route_id",
        "exception_class",
        "exception_stack",
    }
    assert payload["level"] == "ERROR"
    assert payload["logger"] == "ai_gateway.redaction-test"
    assert payload["route_id"] == 42
    assert payload["exception_class"] == "RuntimeError"
    assert payload["exception_stack"]
    assert set(payload["exception_stack"][-1]) == {"file", "function", "line"}
    serialized = json.dumps(payload)
    for secret in (
        "bearer-secret",
        "provider-secret",
        "jwt.secret",
        "fernet-ciphertext",
        "secret-prompt",
        "user:pass",
        "database-password-must-not-leak",
    ):
        assert secret not in serialized


def test_json_log_message_formatting_fails_closed() -> None:
    class UnsafeValue:
        def __str__(self) -> str:
            raise RuntimeError("body-secret-must-not-leak")

    record = logging.LogRecord(
        "ai_gateway.fail-closed",
        logging.ERROR,
        __file__,
        1,
        "unsafe=%s",
        (UnsafeValue(),),
        None,
    )

    serialized = JsonLogFormatter().format(record)

    assert json.loads(serialized)["event"] == "[REDACTED]"
    assert "body-secret-must-not-leak" not in serialized


async def test_global_error_handlers_return_stable_safe_envelopes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app: FastAPI = create_app()

    @app.get("/_test/validation")
    async def validation_error(value: int = Query()) -> int:
        return value

    @app.get("/_test/auth")
    async def auth_error() -> None:
        raise HTTPException(401, {"code": "invalid_token", "message": "Invalid token"})

    @app.get("/_test/timeout")
    async def timeout_error() -> None:
        raise TimeoutError("upstream secret timeout")

    @app.get("/_test/database")
    async def database_error() -> None:
        raise SQLAlchemyError("credential-url=mysql://user:pass@example.test/db")

    @app.get("/_test/unexpected")
    async def unexpected_error() -> None:
        raise RuntimeError("database-password-must-not-leak")

    error_logger = logging.getLogger("ai_gateway.core.errors")
    error_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger="ai_gateway.core.errors"):
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                validation = await client.get("/_test/validation")
                auth = await client.get("/_test/auth")
                database = await client.get("/_test/database")
                timeout = await client.get("/_test/timeout")
                unexpected = await client.get("/_test/unexpected")
    finally:
        error_logger.removeHandler(caplog.handler)

    assert validation.status_code == 422
    assert set(validation.json()) == {"detail"}
    assert set(validation.json()["detail"][0]) == {"loc", "msg", "type"}
    assert auth.status_code == 401
    assert auth.json()["detail"]["code"] == "invalid_token"
    assert database.status_code == 503
    assert database.json()["detail"]["code"] == "database_unavailable"
    assert timeout.status_code == 504
    assert timeout.json()["detail"]["code"] == "timeout"
    assert unexpected.status_code == 500
    assert unexpected.json()["detail"]["code"] == "internal_error"
    request_id = unexpected.json()["detail"]["request_id"]
    assert request_id == unexpected.headers["x-request-id"]
    for response in (validation, auth, database, timeout, unexpected):
        assert str(UUID(response.headers["x-request-id"])) == response.headers["x-request-id"]
    assert current_request_id() is None
    assert "database-password-must-not-leak" not in unexpected.text
    unexpected_record = next(
        record
        for record in caplog.records
        if record.getMessage() == "Unhandled application exception"
    )
    assert unexpected_record.exc_info is not None
