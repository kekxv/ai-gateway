from __future__ import annotations

import json
import logging
import re
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_route_id: ContextVar[int | None] = ContextVar("route_id", default=None)
_record_factory_installed = False
_original_record_factory: Callable[..., logging.LogRecord] | None = None

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|token|"
    r"encrypted(?:[_-]?[a-z0-9]+)?|credentials?|request[_-]?body|response[_-]?body|"
    r"body|secret|password|database[_-]?url)\b\s*[:=]\s*"
    r"(?:\{[^}]*\}|\[[^]]*\]|.*?)(?=\s+[a-z][a-z0-9_-]*\s*[:=]|$)"
)
_URL_CREDENTIALS = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+:[^/@\s]+@")
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_API_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def current_request_id() -> str | None:
    return _request_id.get()


def current_route_id() -> int | None:
    return _route_id.get()


@contextmanager
def log_context(*, request_id: str | None = None, route_id: int | None = None) -> Iterator[None]:
    request_token: Token[str | None] | None = None
    route_token: Token[int | None] | None = None
    if request_id is not None:
        request_token = _request_id.set(request_id)
    if route_id is not None:
        route_token = _route_id.set(route_id)
    try:
        yield
    finally:
        if route_token is not None:
            _route_id.reset(route_token)
        if request_token is not None:
            _request_id.reset(request_token)


def sanitize_log_event(value: object) -> str:
    try:
        event = str(value)
    except Exception:
        return "[REDACTED]"
    event = _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", event)
    event = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", event)
    event = _BEARER_TOKEN.sub("Bearer [REDACTED]", event)
    event = _API_KEY.sub("[REDACTED]", event)
    return _JWT.sub("[REDACTED]", event)


class JsonLogFormatter(logging.Formatter):
    """Serialize a deliberately small, non-sensitive application log schema."""

    def format(self, record: logging.LogRecord) -> str:
        exception_class = getattr(record, "exception_class", None)
        if (
            exception_class is None
            and record.exc_info is not None
            and record.exc_info[0] is not None
        ):
            exception_class = record.exc_info[0].__name__
        if not isinstance(exception_class, str):
            exception_class = None
        request_id = getattr(record, "request_id", current_request_id())
        if not isinstance(request_id, str):
            request_id = None
        route_id = getattr(record, "route_id", current_route_id())
        if not isinstance(route_id, int):
            route_id = None
        try:
            message: object = record.getMessage()
        except Exception:
            message = "[REDACTED]"
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": sanitize_log_event(message),
            "request_id": request_id,
            "route_id": route_id,
            "exception_class": exception_class,
        }
        exception_stack = _safe_exception_stack(record)
        if exception_stack is not None:
            payload["exception_stack"] = exception_stack
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _safe_exception_stack(record: logging.LogRecord) -> list[dict[str, str | int]] | None:
    if record.exc_info is None or record.exc_info[2] is None:
        return None
    try:
        frames = traceback.extract_tb(record.exc_info[2])
    except Exception:
        return []
    return [
        {
            "file": frame.filename.rsplit("/", maxsplit=1)[-1].rsplit("\\", maxsplit=1)[-1],
            "function": frame.name,
            "line": frame.lineno or 0,
        }
        for frame in frames
    ]


def install_log_context() -> None:
    global _original_record_factory, _record_factory_installed
    if _record_factory_installed:
        return
    _original_record_factory = logging.getLogRecordFactory()

    def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        assert _original_record_factory is not None
        record = _original_record_factory(*args, **kwargs)
        record.request_id = current_request_id()
        record.route_id = current_route_id()
        return record

    logging.setLogRecordFactory(record_factory)
    _record_factory_installed = True


def configure_logging(*, level: str = "INFO") -> None:
    install_log_context()
    application_logger = logging.getLogger("ai_gateway")
    application_logger.setLevel(level.upper())
    application_logger.propagate = False
    if not any(
        getattr(handler, "_ai_gateway_json", False) for handler in application_logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        handler._ai_gateway_json = True  # type: ignore[attr-defined]
        application_logger.addHandler(handler)
