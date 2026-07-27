from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from sqlalchemy import Boolean


class OperationRecorder:
    def __init__(self) -> None:
        self.added: list[tuple[str, object]] = []
        self.dropped: list[tuple[str, str]] = []

    def add_column(self, table: str, column: object) -> None:
        self.added.append((table, column))

    def drop_column(self, table: str, column: str) -> None:
        self.dropped.append((table, column))


def load_migration():
    path = Path("migrations/versions/0008_provider_protocol_supports_responses.py")
    spec = spec_from_file_location("migration_0008", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load migration at {path}")
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_0008_adds_non_nullable_responses_capability_with_true_default(monkeypatch) -> None:
    migration = load_migration()
    recorder = OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()

    assert len(recorder.added) == 1
    table, column = recorder.added[0]
    assert table == "provider_protocols"
    assert column.name == "supports_responses"
    assert isinstance(column.type, Boolean)
    assert column.nullable is False
    assert str(column.server_default.arg) == "1"


def test_0008_downgrade_removes_responses_capability(monkeypatch) -> None:
    migration = load_migration()
    recorder = OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.downgrade()

    assert recorder.dropped == [("provider_protocols", "supports_responses")]
