"""Database-backed per-client rate limiting for sensitive endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Request, status
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.service import raise_auth_error
from ai_gateway.db.models import AuthRateLimit


def client_ip(request: Request) -> str:
    """Use the peer address after the server's trusted proxy processing."""
    if request.client is not None:
        return request.client.host
    return "unknown"


async def check_rate_limit(
    request: Request,
    session: AsyncSession,
    *,
    max_requests: int,
    window_seconds: int,
    code: str,
    message: str,
) -> None:
    """Persist and enforce one fixed-window request budget across all replicas."""
    key = client_ip(request)
    now = datetime.now(UTC).replace(tzinfo=None)
    await session.execute(
        insert(AuthRateLimit)
        .values(
            client_key=key,
            window_started_at=now,
            request_count=0,
        )
        .on_duplicate_key_update(client_key=AuthRateLimit.client_key)
    )
    bucket = await session.scalar(
        select(AuthRateLimit)
        .where(AuthRateLimit.client_key == key)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if bucket is None:
        raise RuntimeError("authentication rate-limit row was not created")

    window_expired = bucket.window_started_at <= now - timedelta(seconds=window_seconds)
    if window_expired:
        bucket.window_started_at = now
        bucket.request_count = 1
        allowed = True
    elif bucket.request_count < max_requests:
        bucket.request_count += 1
        allowed = True
    else:
        allowed = False
    await session.commit()

    if not allowed:
        raise_auth_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            code,
            message,
        )
