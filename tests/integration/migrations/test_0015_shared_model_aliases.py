from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine


def _upgrade_to_0015(connection: Connection) -> None:
    path = Path("migrations/versions/0015_shared_model_aliases.py")
    spec = spec_from_file_location("migration_0015", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load migration 0015")
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = Operations(MigrationContext.configure(connection))
    migration.upgrade()


def _downgrade_from_0015(connection: Connection) -> None:
    path = Path("migrations/versions/0015_shared_model_aliases.py")
    spec = spec_from_file_location("migration_0015", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load migration 0015")
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = Operations(MigrationContext.configure(connection))
    migration.downgrade()


async def test_migration_0015_allows_a_shared_alias_after_upgrade(
    test_engine: AsyncEngine,
) -> None:
    """Upgrade drops the live legacy unique-constraint name before inserting duplicates."""
    async with test_engine.begin() as connection:
        await connection.execute(text("DROP INDEX ix_model_aliases_alias ON model_aliases"))
        await connection.execute(
            text(
                "ALTER TABLE model_aliases "
                "ADD CONSTRAINT legacy_model_aliases_alias_unique UNIQUE (alias)"
            )
        )
        await connection.run_sync(_upgrade_to_0015)
        await connection.execute(
            text(
                "INSERT INTO models (canonical_name, display_name) "
                "VALUES ('migration-shared-model-a', 'Migration Model A'), "
                "('migration-shared-model-b', 'Migration Model B')"
            )
        )
        model_ids = (
            await connection.scalars(
                text(
                    "SELECT id FROM models "
                    "WHERE canonical_name IN "
                    "('migration-shared-model-a', 'migration-shared-model-b') "
                    "ORDER BY canonical_name"
                )
            )
        ).all()
        await connection.execute(
            text(
                "INSERT INTO model_aliases (model_id, alias) "
                "VALUES (:model_a, 'shared-chat'), (:model_b, 'shared-chat')"
            ),
            {"model_a": model_ids[0], "model_b": model_ids[1]},
        )

        alias_count = await connection.scalar(
            text("SELECT COUNT(*) FROM model_aliases WHERE alias = 'shared-chat'")
        )

    assert alias_count == 2


async def test_migration_0015_downgrade_refuses_shared_aliases_before_dropping_index(
    test_engine: AsyncEngine,
) -> None:
    async with test_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO models (canonical_name, display_name) "
                "VALUES ('downgrade-shared-model-a', 'Downgrade Model A'), "
                "('downgrade-shared-model-b', 'Downgrade Model B')"
            )
        )
        model_ids = (
            await connection.scalars(
                text(
                    "SELECT id FROM models "
                    "WHERE canonical_name IN "
                    "('downgrade-shared-model-a', 'downgrade-shared-model-b') "
                    "ORDER BY canonical_name"
                )
            )
        ).all()
        await connection.execute(
            text(
                "INSERT INTO model_aliases (model_id, alias) "
                "VALUES (:model_a, 'downgrade-shared-chat'), "
                "(:model_b, 'downgrade-shared-chat')"
            ),
            {"model_a": model_ids[0], "model_b": model_ids[1]},
        )

        with pytest.raises(RuntimeError, match="shared aliases"):
            await connection.run_sync(_downgrade_from_0015)

        index_count = await connection.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'model_aliases' "
                "AND index_name = 'ix_model_aliases_alias'"
            )
        )

    assert index_count == 1
