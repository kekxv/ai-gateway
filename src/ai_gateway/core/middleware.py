from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import Request, Response

from ai_gateway.core.errors import unexpected_error_handler
from ai_gateway.core.logging import log_context

REQUEST_ID_HEADER = "x-request-id"


def request_id_from_header(value: str | None) -> str:
    if value is not None:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


async def correlation_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request_id_from_header(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = request_id
    with log_context(request_id=request_id):
        try:
            response = await call_next(request)
        except Exception as exc:
            response = await unexpected_error_handler(request, exc)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
