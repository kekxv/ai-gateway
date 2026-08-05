from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

INDEX_NAMES = (
    "ix_request_logs_created_at",
    "ix_request_logs_model_created_at",
)
FIXTURE_MODEL_FOREIGN_KEY_INDEX = "ix_request_logs_model_id_fixture"


def _run_0017(connection: Connection, operation: str) -> None:
    path = Path("migrations/versions/0017_billing_statistics_indexes.py")
    spec = spec_from_file_location("migration_0017", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load migration 0017")
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = Operations(MigrationContext.configure(connection))
    getattr(migration, operation)()


def _index_columns(connection: Connection) -> dict[str, list[str]]:
    return {
        index["name"]: index["column_names"]
        for index in inspect(connection).get_indexes("request_logs")
    }


async def test_migration_0017_adds_and_removes_billing_statistics_indexes(
    test_engine: AsyncEngine,
) -> None:
    async with test_engine.begin() as connection:
        existing_indexes = await connection.run_sync(_index_columns)
        await connection.execute(
            text("CREATE INDEX ix_request_logs_model_id_fixture ON request_logs (model_id)")
        )
        for index_name in INDEX_NAMES:
            if index_name in existing_indexes:
                await connection.execute(text(f"DROP INDEX {index_name} ON request_logs"))

        await connection.run_sync(_run_0017, "upgrade")
        upgraded_indexes = await connection.run_sync(_index_columns)

        await connection.run_sync(_run_0017, "downgrade")
        downgraded_indexes = await connection.run_sync(_index_columns)

        await connection.run_sync(_run_0017, "upgrade")
        await connection.execute(
            text(f"DROP INDEX {FIXTURE_MODEL_FOREIGN_KEY_INDEX} ON request_logs")
        )

    assert upgraded_indexes["ix_request_logs_created_at"] == ["created_at"]
    assert upgraded_indexes["ix_request_logs_model_created_at"] == ["model_id", "created_at"]
    assert "ix_request_logs_created_at" not in downgraded_indexes
    assert "ix_request_logs_model_created_at" not in downgraded_indexes
    assert "ix_request_logs_api_key_created_at" in downgraded_indexes
    assert "ix_request_logs_provider_created_at" in downgraded_indexes
