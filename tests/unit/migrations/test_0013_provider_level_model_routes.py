from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


class OperationRecorder:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.dropped_constraints: list[tuple[str, str, str | None]] = []
        self.created_constraints: list[tuple[str, str, tuple[str, ...]]] = []
        self.dropped_columns: list[tuple[str, str]] = []
        self.added_columns: list[tuple[str, object]] = []
        self.altered_columns: list[tuple[str, str, dict[str, object]]] = []

    def get_bind(self) -> object:
        return object()

    def execute(self, statement: str) -> None:
        self.executed.append(" ".join(statement.split()))

    def drop_constraint(self, name: str, table: str, *, type_: str | None = None) -> None:
        self.dropped_constraints.append((name, table, type_))

    def create_unique_constraint(self, name: str, table: str, columns: list[str]) -> None:
        self.created_constraints.append((name, table, tuple(columns)))

    def create_foreign_key(
        self,
        name: str,
        source: str,
        referent: str,
        local_cols: list[str],
        remote_cols: list[str],
    ) -> None:
        self.created_constraints.append(
            (name, f"{source}->{referent}", tuple([*local_cols, *remote_cols]))
        )

    def drop_column(self, table: str, column: str) -> None:
        self.dropped_columns.append((table, column))

    def add_column(self, table: str, column: object) -> None:
        self.added_columns.append((table, column))

    def alter_column(self, table: str, column: str, **kwargs: object) -> None:
        self.altered_columns.append((table, column, kwargs))


class Inspector:
    def get_foreign_keys(self, table: str) -> list[dict[str, object]]:
        assert table == "model_routes"
        return [
            {
                "name": "model_routes_ibfk_3",
                "constrained_columns": ["provider_protocol_id"],
            }
        ]


def load_migration():
    path = Path("migrations/versions/0013_provider_level_model_routes.py")
    spec = spec_from_file_location("migration_0013", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load migration at {path}")
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_upgrade_repoints_history_keeps_smallest_route_and_removes_protocol_fk(
    monkeypatch,
) -> None:
    migration = load_migration()
    recorder = OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)
    monkeypatch.setattr(migration.sa, "inspect", lambda _: Inspector())

    migration.upgrade()

    assert "MIN(id) AS keeper_id" in recorder.executed[0]
    assert "UPDATE request_logs" in recorder.executed[1]
    assert "DELETE model_routes" in recorder.executed[2]
    assert recorder.dropped_constraints == [
        ("model_routes_ibfk_3", "model_routes", "foreignkey"),
        ("uq_model_routes_model_provider_protocol", "model_routes", "unique"),
    ]
    assert recorder.dropped_columns == [("model_routes", "provider_protocol_id")]
    assert recorder.created_constraints == [
        (
            "uq_model_routes_model_provider",
            "model_routes",
            ("model_id", "provider_id"),
        )
    ]


def test_downgrade_restores_a_provider_protocol_reference(monkeypatch) -> None:
    migration = load_migration()
    recorder = OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.downgrade()

    assert recorder.dropped_constraints == [
        ("uq_model_routes_model_provider", "model_routes", "unique")
    ]
    assert recorder.added_columns[0][0] == "model_routes"
    assert "MIN(provider_protocols.id)" in recorder.executed[0]
    assert recorder.altered_columns[0][2]["nullable"] is False
    assert recorder.created_constraints == [
        (
            "fk_model_routes_provider_protocol_id_provider_protocols",
            "model_routes->provider_protocols",
            ("provider_protocol_id", "id"),
        ),
        (
            "uq_model_routes_model_provider_protocol",
            "model_routes",
            ("model_id", "provider_id", "provider_protocol_id"),
        ),
    ]
