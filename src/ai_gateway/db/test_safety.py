from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_gateway.db.base import Base


class UnsafeTestDatabaseError(RuntimeError):
    pass


def validate_test_database_url(database_url: str, application_url: str | None) -> str:
    database = make_url(database_url).database or ""
    if "test" not in database.lower():
        raise UnsafeTestDatabaseError(
            "GATEWAY_TEST_DATABASE_URL must name a dedicated test database"
        )
    if application_url is not None and make_url(application_url).database == database:
        raise UnsafeTestDatabaseError("test and application database names must differ")
    return database


async def assert_test_database_is_disposable(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        table_names = set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
        allowed_test_tables = {*Base.metadata.tables, "alembic_version"}
        unexpected = table_names - allowed_test_tables
        if unexpected:
            raise UnsafeTestDatabaseError(
                f"test database contains non-gateway tables: {sorted(unexpected)!r}"
            )
        for table_name in sorted(table_names & set(Base.metadata.tables)):
            has_rows = await connection.scalar(
                text(f"SELECT 1 FROM `{table_name}` LIMIT 1")  # noqa: S608 - metadata names only
            )
            if has_rows is not None:
                raise UnsafeTestDatabaseError(
                    "test database contains existing data; refusing destructive test setup"
                )


async def clean_test_database(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
