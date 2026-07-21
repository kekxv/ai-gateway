from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_gateway.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return get_engine_for_url(get_settings().database_url)


@lru_cache
def get_engine_for_url(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return get_session_factory_for_url(get_settings().database_url)


@lru_cache
def get_session_factory_for_url(database_url: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine_for_url(database_url), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session
