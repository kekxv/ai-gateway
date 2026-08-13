from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


class OperationRecorder:
    def __init__(self) -> None:
        self.added_columns: list[tuple[str, object]] = []
        self.dropped_columns: list[tuple[str, str]] = []

    def add_column(self, table: str, column: object) -> None:
        self.added_columns.append((table, column))

    def drop_column(self, table: str, column: str) -> None:
        self.dropped_columns.append((table, column))


def _migration():
    path = Path("migrations/versions/0020_add_model_type.py")
    spec = spec_from_file_location("migration_0020", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_adds_text_defaulted_model_type_and_reverses(monkeypatch) -> None:
    migration = _migration()
    recorder = OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()
    assert recorder.added_columns[0][0] == "models"
    column = recorder.added_columns[0][1]
    assert getattr(column, "name") == "model_type"
    assert getattr(column, "nullable") is False
    assert str(getattr(column, "server_default").arg) == "'text'"

    migration.downgrade()
    assert recorder.dropped_columns == [("models", "model_type")]
