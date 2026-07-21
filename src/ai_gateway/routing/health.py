from __future__ import annotations

import re
import socket
import ssl
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
from sqlalchemy import case, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.enums import RouteRuntimeState
from ai_gateway.db.models import ModelRoute
from ai_gateway.routing.sessions import MutationSessionFactory, mutation_session_factory_for
from ai_gateway.routing.types import RouteFailure

Clock = Callable[[], datetime]
PENALIZING_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _status_code(failure: object) -> int | None:
    if isinstance(failure, bool):
        return None
    if isinstance(failure, int):
        return failure
    if isinstance(failure, RouteFailure):
        return failure.status_code
    status_code = getattr(failure, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(failure, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _exception(failure: object) -> BaseException | None:
    if isinstance(failure, RouteFailure):
        return failure.exception
    return failure if isinstance(failure, BaseException) else None


def is_health_failure(failure: object) -> bool:
    status_code = _status_code(failure)
    if status_code is not None:
        return status_code in PENALIZING_HTTP_STATUSES
    exception = _exception(failure)
    return isinstance(
        exception,
        (
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.ConnectError,
            ConnectionError,
            socket.gaierror,
            ssl.SSLError,
        ),
    )


def health_failure_code(failure: object) -> str:
    status_code = _status_code(failure)
    if status_code is not None:
        return f"http_{status_code}"

    exception = _exception(failure)
    if isinstance(exception, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(exception, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(exception, httpx.WriteTimeout):
        return "write_timeout"
    if isinstance(exception, httpx.PoolTimeout):
        return "pool_timeout"
    if isinstance(exception, TimeoutError):
        return "unspecified_timeout"
    if isinstance(exception, socket.gaierror):
        return "dns_error"
    if isinstance(exception, ssl.SSLError):
        return "tls_error"
    if isinstance(exception, (httpx.ConnectError, ConnectionError)):
        return "connect_error"
    if isinstance(exception, httpx.WriteError):
        return "write_error"
    if isinstance(exception, httpx.ReadError):
        return "read_error"
    if isinstance(failure, RouteFailure) and failure.error_code:
        sanitized = re.sub(r"[^a-z0-9_]+", "_", failure.error_code.lower()).strip("_")
        if sanitized:
            return sanitized[:100]
    return "upstream_error"


class RouteHealth:
    def __init__(
        self,
        session: AsyncSession,
        *,
        failure_threshold: int = 3,
        cooldown: timedelta = timedelta(seconds=60),
        clock: Clock = _utcnow,
        mutation_session_factory: MutationSessionFactory | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if cooldown <= timedelta(0):
            raise ValueError("cooldown must be positive")
        self._mutation_session_factory = (
            mutation_session_factory
            if mutation_session_factory is not None
            else mutation_session_factory_for(session)
        )
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown
        self._clock = clock

    async def record_success(self, route_id: int) -> bool:
        async with self._mutation_session_factory() as mutation_session:
            async with mutation_session.begin():
                result = await mutation_session.execute(
                    update(ModelRoute)
                    .where(ModelRoute.id == route_id)
                    .values(
                        consecutive_failures=0,
                        runtime_state=RouteRuntimeState.CLOSED,
                        disabled_until=None,
                        last_error_code=None,
                        last_error_at=None,
                    )
                )
                changed = cast(CursorResult[Any], result).rowcount == 1
        return changed

    async def record_failure(self, route_id: int, failure: object) -> bool:
        if not is_health_failure(failure):
            return False

        now = self._clock()
        async with self._mutation_session_factory() as mutation_session:
            next_failure_count = ModelRoute.consecutive_failures + 1
            opens_route = (ModelRoute.runtime_state == RouteRuntimeState.HALF_OPEN) | (
                next_failure_count >= self._failure_threshold
            )
            async with mutation_session.begin():
                result = await mutation_session.execute(
                    update(ModelRoute)
                    .where(ModelRoute.id == route_id)
                    .ordered_values(
                        (
                            ModelRoute.disabled_until,
                            case(
                                (opens_route, now + self._cooldown),
                                else_=ModelRoute.disabled_until,
                            ),
                        ),
                        (
                            ModelRoute.runtime_state,
                            case(
                                (opens_route, RouteRuntimeState.OPEN),
                                else_=ModelRoute.runtime_state,
                            ),
                        ),
                        (
                            ModelRoute.consecutive_failures,
                            next_failure_count,
                        ),
                        (ModelRoute.last_error_code, health_failure_code(failure)),
                        (ModelRoute.last_error_at, now),
                    )
                )
                changed = cast(CursorResult[Any], result).rowcount == 1
        return changed


HealthManager = RouteHealth


async def record_success(session: AsyncSession, route_id: int) -> bool:
    return await RouteHealth(session).record_success(route_id)


async def record_failure(session: AsyncSession, route_id: int, failure: Any) -> bool:
    return await RouteHealth(session).record_failure(route_id, failure)
