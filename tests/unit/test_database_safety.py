import pytest
from sqlalchemy.pool import NullPool

from ai_gateway.db.session import get_session_factory_for_url
from ai_gateway.db.test_safety import UnsafeTestDatabaseError, validate_test_database_url


def test_test_database_guard_rejects_application_or_non_test_schema() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="dedicated test database"):
        validate_test_database_url(
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway",
            None,
        )
    with pytest.raises(UnsafeTestDatabaseError, match="must differ"):
        validate_test_database_url(
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test",
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test",
        )


def test_test_database_guard_accepts_dedicated_schema() -> None:
    assert (
        validate_test_database_url(
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test",
            "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway",
        )
        == "gateway_test"
    )


def test_standalone_session_factory_has_no_hidden_connection_pool() -> None:
    factory = get_session_factory_for_url(
        "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test"
    )

    assert isinstance(factory.kw["bind"].pool, NullPool)
