from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_gateway.core.config import get_settings


def get_engine() -> AsyncEngine:
    return get_engine_for_url(get_settings().database_url)


def get_engine_for_url(database_url: str) -> AsyncEngine:
    """Create an engine for one explicit owner.

    Engines deliberately are not cached by URL: pooled async connections are bound to
    the event loop that opened them and must be disposed by their application owner.
    """
    return create_async_engine(database_url, pool_pre_ping=True)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return get_session_factory_for_url(get_settings().database_url)


def get_session_factory_for_url(database_url: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine_for_url(database_url), expire_on_commit=False)


def get_session_factory_for_engine(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session
