import asyncio
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import cast

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ai_gateway import main as main_module
from ai_gateway.core.config import Settings
from ai_gateway.main import REQUIRED_MIGRATION_HEAD, create_app, verify_database


def test_required_migration_head_matches_alembic_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert REQUIRED_MIGRATION_HEAD == script.get_current_head()


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
        self.dispose_calls = 0

    def connect(self) -> StubConnectionContext:
        return StubConnectionContext(self.connection)

    async def dispose(self) -> None:
        self.dispose_calls += 1


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
    with pytest.raises(RuntimeError, match=REQUIRED_MIGRATION_HEAD):
        await verify_database(cast(AsyncEngine, StubEngine(outdated)))

    unavailable = StubConnection(set(), error=SQLAlchemyError("database down"))
    with pytest.raises(RuntimeError, match="connectivity or migration"):
        await verify_database(cast(AsyncEngine, StubEngine(unavailable)))

    explicitly_bypassed = StubConnection({"outdated-but-ignored"})
    await verify_database(
        cast(AsyncEngine, StubEngine(explicitly_bypassed)),
        require_migration_head=False,
    )
    assert explicitly_bypassed.statements == ["SELECT 1"]


async def test_non_production_startup_still_requires_current_migration_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = StubEngine(StubConnection({"0003"}))
    monkeypatch.setattr(
        main_module,
        "get_engine_for_url",
        lambda _, **__: cast(AsyncEngine, engine),
    )
    app = create_app(runtime_settings(environment="development"))

    with pytest.raises(RuntimeError, match=REQUIRED_MIGRATION_HEAD):
        async with app.router.lifespan_context(app):
            pytest.fail("development startup accepted an outdated migration")

    assert engine.dispose_calls == 1


async def test_lifespan_starts_and_closes_shared_resources_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokenizer_warm_calls = 0

    async def warm_tokenizer() -> None:
        nonlocal tokenizer_warm_calls
        tokenizer_warm_calls += 1

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

    engine = StubEngine(StubConnection({REQUIRED_MIGRATION_HEAD}))

    async def verified(_: AsyncEngine, *, require_migration_head: bool) -> None:
        assert require_migration_head is True
        return None

    monkeypatch.setattr(
        main_module,
        "get_engine_for_url",
        lambda _, **__: cast(AsyncEngine, engine),
    )
    monkeypatch.setattr(main_module, "verify_database", verified)
    monkeypatch.setattr(main_module, "HttpClientFactory", StubHttpClientFactory)
    monkeypatch.setattr(main_module, "ModelSyncScheduler", StubModelSyncScheduler)
    monkeypatch.setattr(main_module, "BillingRecoveryScheduler", StubBillingRecoveryScheduler)
    monkeypatch.setattr(main_module, "warm_tokenizer", warm_tokenizer, raising=False)
    app = create_app(runtime_settings())

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(schedulers[0].started.wait(), timeout=1)
        await asyncio.wait_for(recovery_schedulers[0].started.wait(), timeout=1)
        assert factories[0].close_calls == 0

    assert len(factories) == len(schedulers) == len(recovery_schedulers) == 1
    assert factories[0].close_calls == 1
    assert schedulers[0].run_calls == schedulers[0].stop_calls == 1
    assert recovery_schedulers[0].run_calls == recovery_schedulers[0].stop_calls == 1
    assert tokenizer_warm_calls == 1
    assert engine.dispose_calls == 1


def test_multiple_apps_own_distinct_engines_across_event_loops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engines: list[StubEngine] = []

    def create_engine(_: str, **kwargs: object) -> AsyncEngine:
        assert kwargs == {
            "pool_size": 20,
            "max_overflow": 20,
            "pool_timeout": 30.0,
            "pool_recycle": 1800,
        }
        engine = StubEngine(StubConnection({REQUIRED_MIGRATION_HEAD}))
        engines.append(engine)
        return cast(AsyncEngine, engine)

    async def verified(_: AsyncEngine, *, require_migration_head: bool) -> None:
        assert require_migration_head is True

    class StubHttpClientFactory:
        def __init__(self, _: Settings) -> None:
            pass

        async def aclose(self) -> None:
            return None

    class StubScheduler:
        def __init__(self, *_: object, **__: object) -> None:
            self.stopped = asyncio.Event()

        async def run(self) -> None:
            await self.stopped.wait()

        def stop(self) -> None:
            self.stopped.set()

    monkeypatch.setattr(main_module, "get_engine_for_url", create_engine)
    monkeypatch.setattr(main_module, "verify_database", verified)
    monkeypatch.setattr(main_module, "HttpClientFactory", StubHttpClientFactory)
    monkeypatch.setattr(main_module, "ModelSyncScheduler", StubScheduler)
    monkeypatch.setattr(main_module, "BillingRecoveryScheduler", StubScheduler)
    apps = [create_app(runtime_settings()), create_app(runtime_settings())]

    async def start_and_stop(app: FastAPI) -> None:
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0)

    for app in apps:
        asyncio.run(start_and_stop(app))

    assert len(engines) == 2
    assert engines[0] is not engines[1]
    assert [engine.dispose_calls for engine in engines] == [1, 1]


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


async def test_initialized_health_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(runtime_settings())

    async def available(_: object) -> bool:
        return True

    monkeypatch.setattr(main_module, "database_is_available", available)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
