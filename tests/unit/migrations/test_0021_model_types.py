from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa


class OperationRecorder:
    def __init__(self) -> None:
        self.added_columns: list[tuple[str, object]] = []
        self.altered_columns: list[tuple[str, str, dict[str, object]]] = []
        self.executed_sql: list[str] = []
        self.dropped_columns: list[tuple[str, str]] = []

    def add_column(self, table: str, column: object) -> None:
        self.added_columns.append((table, column))

    def alter_column(self, table: str, column: str, **kwargs: object) -> None:
        self.altered_columns.append((table, column, kwargs))

    def execute(self, sql: object) -> None:
        self.executed_sql.append(str(sql))

    def drop_column(self, table: str, column: str) -> None:
        self.dropped_columns.append((table, column))


def _migration():
    path = Path("migrations/versions/0021_model_types.py")
    spec = spec_from_file_location("migration_0021", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_backfills_and_reverses_model_types(monkeypatch) -> None:
    migration = _migration()
    recorder = OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()

    assert recorder.added_columns[0][0] == "models"
    column = recorder.added_columns[0][1]
    assert getattr(column, "name") == "model_types"
    assert getattr(column, "nullable") is True
    assert recorder.executed_sql == ["UPDATE models SET model_types = JSON_ARRAY(model_type)"]
    assert recorder.altered_columns[0][:2] == ("models", "model_types")
    assert recorder.altered_columns[0][2]["nullable"] is False
    assert isinstance(recorder.altered_columns[0][2]["existing_type"], sa.JSON)

    migration.downgrade()

    assert recorder.executed_sql[-1] == (
        "UPDATE models SET model_type = JSON_UNQUOTE(JSON_EXTRACT(model_types, '$[0]'))"
    )
    assert recorder.dropped_columns == [("models", "model_types")]
