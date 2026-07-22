import asyncio
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import cast

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ai_gateway import main as main_module
from ai_gateway.core.config import Settings
from ai_gateway.main import REQUIRED_MIGRATION_HEAD, create_app, verify_database


class StubConnection:
    def __init__(
        self,
        revisions: set[str],
        *,
        error: SQLAlchemyError | None = None,
    ) -> None:
        self.revisions = revisions
        self.error = error
        self.statements: list[str] = []

    async def execute(self, statement: object) -> None:
        self.statements.append(str(statement))
        if self.error is not None:
            raise self.error

    async def scalars(self, statement: object) -> set[str]:
        self.statements.append(str(statement))
        return self.revisions


class StubConnectionContext(AbstractAsyncContextManager[AsyncConnection]):
    def __init__(self, connection: StubConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> AsyncConnection:
        return cast(AsyncConnection, self.connection)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class StubEngine:
    def __init__(self, connection: StubConnection) -> None:
        self.connection = connection

    def connect(self) -> StubConnectionContext:
        return StubConnectionContext(self.connection)


def runtime_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "test",
        "jwt_secret": "startup-test-jwt-secret-at-least-32-bytes",
        "encryption_key": Fernet.generate_key().decode(),
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "example_value"),
    [
        ("jwt_secret", "replace-with-a-long-random-secret"),
        ("encryption_key", "replace-with-a-fernet-key"),
    ],
)
async def test_production_startup_rejects_example_secrets(
    field: str,
    example_value: str,
) -> None:
    settings = runtime_settings(environment="production", **{field: example_value})
    app = create_app(settings)

    with pytest.raises(RuntimeError, match=field):
        async with app.router.lifespan_context(app):
            pytest.fail("production startup accepted an example secret")


async def test_startup_checks_connectivity_and_required_migration_head() -> None:
    current = StubConnection({REQUIRED_MIGRATION_HEAD})
    await verify_database(cast(AsyncEngine, StubEngine(current)))
    assert current.statements == ["SELECT 1", "SELECT version_num FROM alembic_version"]

    outdated = StubConnection({"0003"})
    with pytest.raises(RuntimeError, match="0004"):
        await verify_database(cast(AsyncEngine, StubEngine(outdated)))

    unavailable = StubConnection(set(), error=SQLAlchemyError("database down"))
    with pytest.raises(RuntimeError, match="connectivity or migration"):
        await verify_database(cast(AsyncEngine, StubEngine(unavailable)))

    non_production = StubConnection({"outdated-but-ignored"})
    await verify_database(
        cast(AsyncEngine, StubEngine(non_production)),
        require_migration_head=False,
    )
    assert non_production.statements == ["SELECT 1"]


async def test_lifespan_starts_and_closes_shared_resources_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubHttpClientFactory:
        def __init__(self, _: Settings) -> None:
            self.close_calls = 0
            factories.append(self)

        async def aclose(self) -> None:
            self.close_calls += 1

    class StubScheduler:
        def __init__(self, *_: object, **__: object) -> None:
            self.run_calls = 0
            self.stop_calls = 0
            self.started = asyncio.Event()
            self.stopped = asyncio.Event()

        async def run(self) -> None:
            self.run_calls += 1
            self.started.set()
            await self.stopped.wait()

        def stop(self) -> None:
            self.stop_calls += 1
            self.stopped.set()

    class StubModelSyncScheduler(StubScheduler):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            schedulers.append(self)

    class StubBillingRecoveryScheduler(StubScheduler):
        def __init__(self, *_: object, **kwargs: object) -> None:
            super().__init__(**kwargs)
            recovery_schedulers.append(self)

    factories: list[StubHttpClientFactory] = []
    schedulers: list[StubScheduler] = []
    recovery_schedulers: list[StubScheduler] = []

    async def verified(_: AsyncEngine, *, require_migration_head: bool) -> None:
        assert require_migration_head is False
        return None

    monkeypatch.setattr(main_module, "verify_database", verified)
    monkeypatch.setattr(main_module, "HttpClientFactory", StubHttpClientFactory)
    monkeypatch.setattr(main_module, "ModelSyncScheduler", StubModelSyncScheduler)
    monkeypatch.setattr(main_module, "BillingRecoveryScheduler", StubBillingRecoveryScheduler)
    app = create_app(runtime_settings())

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(schedulers[0].started.wait(), timeout=1)
        await asyncio.wait_for(recovery_schedulers[0].started.wait(), timeout=1)
        assert factories[0].close_calls == 0

    assert len(factories) == len(schedulers) == len(recovery_schedulers) == 1
    assert factories[0].close_calls == 1
    assert schedulers[0].run_calls == schedulers[0].stop_calls == 1
    assert recovery_schedulers[0].run_calls == recovery_schedulers[0].stop_calls == 1


async def test_health_returns_503_when_database_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = runtime_settings(database_url="mysql+asyncmy://invalid:invalid@127.0.0.1:1/none")
    app = create_app(settings)

    async def fail_database(_: object) -> bool:
        await asyncio.sleep(0)
        return False

    monkeypatch.setattr("ai_gateway.main.database_is_available", fail_database)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
