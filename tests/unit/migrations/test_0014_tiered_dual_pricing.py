from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


class OperationRecorder:
    def __init__(self) -> None:
        self.altered_columns: list[tuple[str, str, dict[str, object]]] = []
        self.added_columns: list[tuple[str, object]] = []
        self.dropped_columns: list[tuple[str, str]] = []
        self.created_tables: list[tuple[str, tuple[object, ...]]] = []
        self.dropped_tables: list[str] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...]]] = []
        self.dropped_indexes: list[tuple[str, str | None]] = []

    def alter_column(self, table: str, column: str, **kwargs: object) -> None:
        self.altered_columns.append((table, column, kwargs))

    def add_column(self, table: str, column: object) -> None:
        self.added_columns.append((table, column))

    def drop_column(self, table: str, column: str) -> None:
        self.dropped_columns.append((table, column))

    def create_table(self, name: str, *columns: object, **_: object) -> None:
        self.created_tables.append((name, columns))

    def drop_table(self, name: str) -> None:
        self.dropped_tables.append(name)

    def create_index(self, name: str, table: str, columns: list[str]) -> None:
        self.created_indexes.append((name, table, tuple(columns)))

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.dropped_indexes.append((name, table_name))


def load_migration():
    path = Path("migrations/versions/0014_tiered_dual_pricing.py")
    spec = spec_from_file_location("migration_0014", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load migration at {path}")
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _column_names(columns: tuple[object, ...]) -> set[str]:
    return {str(getattr(column, "name")) for column in columns if getattr(column, "name", None)}


def test_upgrade_creates_tiers_and_separates_provider_and_request_costs(monkeypatch) -> None:
    migration = load_migration()
    recorder = OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()

    assert recorder.altered_columns[0][0:2] == ("providers", "price_multiplier")
    altered = recorder.altered_columns[0][2]
    assert altered["new_column_name"] == "cost_multiplier"
    assert altered["existing_nullable"] is False
    assert str(altered["existing_type"]) == "NUMERIC(4, 2)"
    assert str(altered["existing_server_default"]) == "1.00"
    assert [(table, getattr(column, "name")) for table, column in recorder.added_columns] == [
        ("providers", "public_multiplier"),
        ("request_logs", "cost_amount"),
    ]
    assert recorder.created_tables[0][0] == "model_price_tiers"
    assert _column_names(recorder.created_tables[0][1]) == {
        "id",
        "model_id",
        "max_input_tokens",
        "input_price_per_million",
        "output_price_per_million",
        "cache_read_price_per_million",
        "cache_write_price_per_million",
    }
    assert recorder.created_indexes == [
        (
            "ix_model_price_tiers_model_max_input",
            "model_price_tiers",
            ("model_id", "max_input_tokens"),
        )
    ]


def test_downgrade_removes_new_data_and_restores_price_multiplier(monkeypatch) -> None:
    migration = load_migration()
    recorder = OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.downgrade()

    assert recorder.dropped_indexes == [
        ("ix_model_price_tiers_model_max_input", "model_price_tiers")
    ]
    assert recorder.dropped_tables == ["model_price_tiers"]
    assert recorder.dropped_columns == [
        ("request_logs", "cost_amount"),
        ("providers", "public_multiplier"),
    ]
    assert recorder.altered_columns[0][0:2] == ("providers", "cost_multiplier")
    assert recorder.altered_columns[0][2]["new_column_name"] == "price_multiplier"
