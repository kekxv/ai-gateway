from unittest.mock import Mock

import pytest
from sqlalchemy.pool import NullPool

from ai_gateway.db import test_safety
from ai_gateway.db.session import get_session_factory_for_url
from ai_gateway.db.test_safety import UnsafeTestDatabaseError, validate_test_database_url


@pytest.mark.parametrize("database", ["contest", "latest", "protest", "testament", "gateway"])
def test_test_database_guard_rejects_names_that_only_contain_test(database: str) -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="dedicated test database"):
        validate_test_database_url(
            f"mysql+asyncmy://gateway:gateway@127.0.0.1:3306/{database}",
            None,
        )


def test_test_database_guard_rejects_normalized_application_schema() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="must differ"):
        validate_test_database_url(
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/Gateway_Test",
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test",
        )


@pytest.mark.parametrize(
    ("database", "expected"),
    [
        ("gateway_test", "gateway_test"),
        ("service_ci_test", "service_ci_test"),
        ("gateway_test_worker_42", "gateway_test_worker_42"),
        ("%20Gateway_Test%20", "gateway_test"),
    ],
)
def test_test_database_guard_accepts_explicit_safe_schema_names(
    database: str, expected: str
) -> None:
    assert (
        validate_test_database_url(
            f"mysql+asyncmy://gateway:gateway@127.0.0.1:3306/{database}",
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway",
        )
        == expected
    )


@pytest.mark.parametrize(
    ("test_url", "application_url"),
    [
        ("mysql+asyncmy://gateway:gateway@127.0.0.1:3306", None),
        (
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test",
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306",
        ),
    ],
)
def test_test_database_guard_rejects_missing_database_target(
    test_url: str, application_url: str | None
) -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="include a database name"):
        validate_test_database_url(test_url, application_url)


def test_safe_test_engine_rejects_before_engine_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    engine_factory = Mock(side_effect=AssertionError("unsafe target reached engine creation"))
    monkeypatch.setattr(test_safety, "create_async_engine", engine_factory, raising=False)

    with pytest.raises(UnsafeTestDatabaseError, match="dedicated test database"):
        test_safety.create_test_engine(
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/contest",
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway",
        )

    engine_factory.assert_not_called()


def test_standalone_session_factory_has_no_hidden_connection_pool() -> None:
    factory = get_session_factory_for_url(
        "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test"
    )

    assert isinstance(factory.kw["bind"].pool, NullPool)
