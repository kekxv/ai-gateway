from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

MutationSessionFactory = Callable[[], AsyncSession]


def mutation_session_factory_for(session: AsyncSession) -> MutationSessionFactory:
    bind = session.bind
    if bind is None:
        raise ValueError("the caller session must be bound to an async engine or connection")
    engine = bind if isinstance(bind, AsyncEngine) else bind.engine
    return async_sessionmaker(engine, expire_on_commit=False)
