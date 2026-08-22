from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


class OperationRecorder:
    def __init__(self) -> None:
        self.created_tables: list[tuple[str, tuple[object, ...]]] = []
        self.created_indexes: list[tuple[str, str, list[str]]] = []
        self.dropped_indexes: list[tuple[str, str]] = []
        self.dropped_tables: list[str] = []

    def create_table(self, name: str, *columns: object, **_: object) -> None:
        self.created_tables.append((name, columns))

    def create_index(self, name: str, table: str, columns: list[str]) -> None:
        self.created_indexes.append((name, table, columns))

    def drop_index(self, name: str, *, table_name: str) -> None:
        self.dropped_indexes.append((name, table_name))

    def drop_table(self, name: str) -> None:
        self.dropped_tables.append(name)


def _migration():
    path = Path("migrations/versions/0023_session_route_affinity.py")
    spec = spec_from_file_location("migration_0023", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_migration_creates_hashed_api_key_scoped_affinity_table(monkeypatch) -> None:
    migration = _migration()
    recorder = OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()

    assert migration.down_revision == "0022"
    table_name, columns = recorder.created_tables[0]
    assert table_name == "session_route_affinities"
    columns_by_name = {getattr(column, "name", None): column for column in columns}
    assert set(columns_by_name) >= {
        "api_key_id",
        "affinity_hash",
        "provider_id",
        "expires_at",
        "updated_at",
    }
    assert getattr(columns_by_name["affinity_hash"].type, "length") == 32
    assert recorder.created_indexes == [
        (
            "ix_session_route_affinities_expires_at",
            "session_route_affinities",
            ["expires_at"],
        )
    ]

    migration.downgrade()

    assert recorder.dropped_indexes == [
        ("ix_session_route_affinities_expires_at", "session_route_affinities")
    ]
    assert recorder.dropped_tables == ["session_route_affinities"]
