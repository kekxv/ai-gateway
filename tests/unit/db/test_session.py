from __future__ import annotations

from typing import Any, cast

import anyio
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.config import Settings
from ai_gateway.db import session as session_module


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "jwt_secret": "database-pool-test-jwt-secret-at-least-32-bytes",
        "encryption_key": Fernet.generate_key().decode(),
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_database_pool_defaults_are_bounded_and_validated() -> None:
    settings = _settings()

    assert settings.database_pool_size == 20
    assert settings.database_max_overflow == 20
    assert settings.database_pool_timeout_seconds == 30.0
    assert settings.database_pool_recycle_seconds == 1800

    for field, value in (
        ("database_pool_size", 0),
        ("database_max_overflow", -1),
        ("database_pool_timeout_seconds", 0),
        ("database_pool_recycle_seconds", 0),
    ):
        with pytest.raises(ValidationError):
            _settings(**{field: value})


def test_engine_forwards_explicit_pool_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    def create_engine(url: str, **kwargs: Any) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(session_module, "create_async_engine", create_engine)
    monkeypatch.setattr(session_module, "configure_database_timezone", lambda engine: engine)

    engine = session_module.get_engine_for_url(
        "mysql+asyncmy://gateway:gateway@mysql/gateway",
        pool_size=7,
        max_overflow=9,
        pool_timeout=4.5,
        pool_recycle=600,
    )

    assert engine is sentinel
    assert captured == {
        "url": "mysql+asyncmy://gateway:gateway@mysql/gateway",
        "pool_pre_ping": True,
        "pool_size": 7,
        "max_overflow": 9,
        "pool_timeout": 4.5,
        "pool_recycle": 600,
    }


async def test_shielded_session_close_finishes_without_consuming_cancellation() -> None:
    class SlowSession:
        def __init__(self) -> None:
            self.close_calls = 0
            self.closed = False

        async def close(self) -> None:
            self.close_calls += 1
            await anyio.sleep(0)
            self.closed = True

    session = SlowSession()
    continued_after_cancel = False
    with anyio.CancelScope() as scope:
        scope.cancel()
        await session_module.close_session_shielded(
            cast(AsyncSession, session),
        )
        await anyio.sleep(0)
        continued_after_cancel = True

    assert session.close_calls == 1
    assert session.closed is True
    assert continued_after_cancel is False
