import logging
from collections.abc import Mapping

import httpx
from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from ai_gateway.core.logging import current_request_id

logger = logging.getLogger(__name__)


class GatewayError(Exception):
    """Base exception for errors that can be exposed by the gateway API."""

    code = "gateway_error"
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def sanitized_request_validation_error_handler(
    _: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": [
                {
                    "loc": list(error["loc"]),
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()
            ]
        },
    )


async def gateway_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, GatewayError):
        raise exc
    return _detail_response(exc.status_code, exc.code, exc.message)


async def http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        raise exc
    detail = exc.detail
    if isinstance(detail, Mapping):
        raw_code = detail.get("code")
        raw_message = detail.get("message")
        code = raw_code if isinstance(raw_code, str) else "http_error"
        message = raw_message if isinstance(raw_message, str) else "Request failed"
        content: object = {"code": code, "message": message}
    elif isinstance(detail, str):
        content = detail
    else:
        content = "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": content},
        headers=exc.headers,
    )


async def database_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, SQLAlchemyError):
        raise exc
    logger.exception(
        "Database request failed",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"exception_class": type(exc).__name__},
    )
    return _detail_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "database_unavailable",
        "Database unavailable",
        include_request_id=True,
    )


async def timeout_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        raise exc
    logger.exception(
        "Request timed out",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"exception_class": type(exc).__name__},
    )
    return _detail_response(
        status.HTTP_504_GATEWAY_TIMEOUT,
        "timeout",
        "Request timed out",
        include_request_id=True,
    )


async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled application exception",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"exception_class": type(exc).__name__},
    )
    return _detail_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "Internal server error",
        include_request_id=True,
    )


def _detail_response(
    status_code: int,
    code: str,
    message: str,
    *,
    include_request_id: bool = False,
) -> JSONResponse:
    detail = {"code": code, "message": message}
    if include_request_id:
        detail["request_id"] = current_request_id() or ""
    return JSONResponse(status_code=status_code, content={"detail": detail})
