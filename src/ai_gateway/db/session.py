from collections.abc import AsyncIterator

import anyio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from ai_gateway.core.config import get_settings


def get_engine() -> AsyncEngine:
    settings = get_settings()
    return get_engine_for_url(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        pool_recycle=settings.database_pool_recycle_seconds,
    )


def get_engine_for_url(
    database_url: str,
    *,
    pool_size: int = 20,
    max_overflow: int = 20,
    pool_timeout: float = 30.0,
    pool_recycle: int = 1800,
) -> AsyncEngine:
    """Create an engine for one explicit owner.

    Engines deliberately are not cached by URL: pooled async connections are bound to
    the event loop that opened them and must be disposed by their application owner.
    """
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return get_session_factory_for_url(get_settings().database_url)


def get_session_factory_for_url(database_url: str) -> async_sessionmaker[AsyncSession]:
    # This compatibility helper has no async owner that can dispose a pooled engine.
    # NullPool makes every session close its connection instead of leaking a hidden pool.
    engine = create_async_engine(database_url, pool_pre_ping=True, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False)


def get_session_factory_for_engine(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        await close_session_shielded(session)


async def close_session_shielded(session: AsyncSession) -> None:
    """Return a connection even when the surrounding request is cancelled."""

    with anyio.CancelScope(shield=True):
        await session.close()
