import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from ai_gateway.db.base import Base
from ai_gateway.db.test_safety import (
    assert_test_database_is_disposable,
    clean_test_database,
    validate_test_database_url,
)


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    database_url = os.getenv("GATEWAY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.fail("GATEWAY_TEST_DATABASE_URL is required for database tests")
    validate_test_database_url(database_url, os.getenv("GATEWAY_DATABASE_URL"))

    engine = create_async_engine(database_url, pool_pre_ping=True, poolclass=NullPool)
    await assert_test_database_is_disposable(engine)
    await clean_test_database(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        )
        await connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0004')"))

    yield engine

    await clean_test_database(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        db_session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield db_session
        finally:
            await db_session.close()
            if transaction.is_active:
                await transaction.rollback()
