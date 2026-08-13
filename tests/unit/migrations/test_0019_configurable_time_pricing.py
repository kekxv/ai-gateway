from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


class OperationRecorder:
    def __init__(self) -> None:
        self.created_tables: list[tuple[str, tuple[object, ...]]] = []
        self.dropped_tables: list[str] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...]]] = []
        self.dropped_indexes: list[tuple[str, str | None]] = []

    def create_table(self, name: str, *columns: object, **_: object) -> None:
        self.created_tables.append((name, columns))

    def drop_table(self, name: str) -> None:
        self.dropped_tables.append(name)

    def create_index(self, name: str, table: str, columns: list[str]) -> None:
        self.created_indexes.append((name, table, tuple(columns)))

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.dropped_indexes.append((name, table_name))


def _migration():
    path = Path("migrations/versions/0019_configurable_time_pricing.py")
    spec = spec_from_file_location("migration_0019", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_creates_and_removes_configurable_time_price_rules(monkeypatch) -> None:
    migration = _migration()
    recorder = OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()
    assert recorder.created_tables[0][0] == "model_time_price_rules"
    columns = {
        str(getattr(column, "name"))
        for column in recorder.created_tables[0][1]
        if getattr(column, "name", None)
    }
    assert columns == {
        "id",
        "model_id",
        "weekdays",
        "start_time",
        "end_time",
        "effective_at",
        "input_price_per_million",
        "output_price_per_million",
        "cache_read_price_per_million",
        "cache_write_price_per_million",
    }
    assert recorder.created_indexes == [
        ("ix_model_time_price_rules_model", "model_time_price_rules", ("model_id",))
    ]

    migration.downgrade()
    assert recorder.dropped_indexes == [
        ("ix_model_time_price_rules_model", "model_time_price_rules")
    ]
    assert recorder.dropped_tables == ["model_time_price_rules"]
