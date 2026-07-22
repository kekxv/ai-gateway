from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote

from sqlalchemy import inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from ai_gateway.db.base import Base


class UnsafeTestDatabaseError(RuntimeError):
    pass


_EXPLICIT_TEST_DATABASE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*_test$")
_GATEWAY_TEMP_TEST_DATABASE = re.compile(r"^gateway_test_[a-z0-9]+(?:_[a-z0-9]+)*$")


def _database_target(database_url: str, setting_name: str) -> tuple[URL, str, str]:
    try:
        url = make_url(database_url)
    except (ArgumentError, ValueError) as exc:
        raise UnsafeTestDatabaseError(f"{setting_name} must be a valid database URL") from exc
    raw_database = url.database
    if not raw_database:
        raise UnsafeTestDatabaseError(f"{setting_name} must include a database name")

    canonical_database = unicodedata.normalize("NFKC", unquote(raw_database)).strip().casefold()
    if not canonical_database:
        raise UnsafeTestDatabaseError(f"{setting_name} must include a database name")
    return url, raw_database, canonical_database


def _validated_test_database_target(
    database_url: str, application_url: str | None
) -> tuple[URL, str]:
    url, raw_database, database = _database_target(database_url, "GATEWAY_TEST_DATABASE_URL")
    if raw_database != database:
        raise UnsafeTestDatabaseError(
            "GATEWAY_TEST_DATABASE_URL database name must be canonical lowercase ASCII"
        )
    if not (
        _EXPLICIT_TEST_DATABASE.fullmatch(database)
        or _GATEWAY_TEMP_TEST_DATABASE.fullmatch(database)
    ):
        raise UnsafeTestDatabaseError(
            "GATEWAY_TEST_DATABASE_URL must name a dedicated test database"
        )
    if application_url is not None:
        _, _, application_database = _database_target(application_url, "GATEWAY_DATABASE_URL")
        if application_database == database:
            raise UnsafeTestDatabaseError("test and application database names must differ")
    return url, database


def validate_test_database_url(database_url: str, application_url: str | None) -> str:
    _, database = _validated_test_database_target(database_url, application_url)
    return database


def create_test_engine(database_url: str, application_url: str | None) -> AsyncEngine:
    url, _ = _validated_test_database_target(database_url, application_url)
    return create_async_engine(url, pool_pre_ping=True, poolclass=NullPool)


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
