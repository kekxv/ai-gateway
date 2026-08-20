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
    path = Path("migrations/versions/0022_provider_http_proxy.py")
    spec = spec_from_file_location("migration_0022", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_adds_nullable_encrypted_provider_proxy(monkeypatch) -> None:
    migration = _migration()
    recorder = OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()

    assert migration.down_revision == "0021"
    table, column = recorder.added_columns[0]
    assert table == "providers"
    assert getattr(column, "name") == "proxy_config_encrypted"
    assert getattr(column, "nullable") is True

    migration.downgrade()

    assert recorder.dropped_columns == [("providers", "proxy_config_encrypted")]
