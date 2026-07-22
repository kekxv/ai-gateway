import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ai_gateway.admin.api_keys import router as api_keys_router
from ai_gateway.admin.billing import router as billing_router
from ai_gateway.admin.dashboard import router as dashboard_router
from ai_gateway.admin.model_sync import router as model_sync_router
from ai_gateway.admin.models import models_router, routes_router
from ai_gateway.admin.providers import router as providers_router
from ai_gateway.admin.request_logs import router as request_logs_router
from ai_gateway.admin.users import router as users_router
from ai_gateway.audit.codec import DEFAULT_AUDIT_BODY_LIMIT_BYTES
from ai_gateway.audit.service import AuditService, use_audit_service
from ai_gateway.auth.router import router as auth_router
from ai_gateway.billing.recovery import BillingRecoveryScheduler
from ai_gateway.billing.service import BillingService
from ai_gateway.catalog.scheduler import ModelSyncScheduler
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.errors import (
    GatewayError,
    database_error_handler,
    gateway_error_handler,
    http_error_handler,
    sanitized_request_validation_error_handler,
    timeout_error_handler,
    unexpected_error_handler,
)
from ai_gateway.core.logging import configure_logging
from ai_gateway.core.middleware import correlation_middleware
from ai_gateway.db.session import (
    get_engine_for_url,
    get_session,
    get_session_factory_for_engine,
)
from ai_gateway.frontend import mount_console
from ai_gateway.gateway.claude import router as claude_gateway_router
from ai_gateway.gateway.gemini import router as gemini_gateway_router
from ai_gateway.gateway.models import router as models_gateway_router
from ai_gateway.gateway.openai import router as openai_gateway_router
from ai_gateway.gateway.websocket import router as websocket_gateway_router
from ai_gateway.transport.http import HttpClientFactory

REQUIRED_MIGRATION_HEAD = "0004"
_EXAMPLE_JWT_SECRET = "replace-with-a-long-random-secret"
_EXAMPLE_ENCRYPTION_KEY = "replace-with-a-fernet-key"


def validate_runtime_settings(settings: Settings) -> None:
    if getattr(settings, "environment", "development") != "production":
        return
    example_fields = {
        "jwt_secret": (settings.jwt_secret.get_secret_value(), _EXAMPLE_JWT_SECRET),
        "encryption_key": (settings.encryption_key.get_secret_value(), _EXAMPLE_ENCRYPTION_KEY),
    }
    for field, (value, example) in example_fields.items():
        if value == example:
            raise RuntimeError(f"Production {field} must not use the example value")


async def verify_database(
    engine: AsyncEngine,
    *,
    require_migration_head: bool = True,
) -> None:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            if not require_migration_head:
                return
            revisions = set(
                await connection.scalars(text("SELECT version_num FROM alembic_version"))
            )
    except SQLAlchemyError as exc:
        raise RuntimeError("Database connectivity or migration check failed") from exc
    if revisions != {REQUIRED_MIGRATION_HEAD}:
        raise RuntimeError(
            f"Database migration head must be {REQUIRED_MIGRATION_HEAD}; run alembic upgrade head"
        )


async def database_is_available(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


def _audit_body_limit(settings: object) -> int:
    return int(getattr(settings, "audit_body_limit_bytes", DEFAULT_AUDIT_BODY_LIMIT_BYTES))


def _billing_default_max_output_tokens(settings: object) -> int:
    return int(getattr(settings, "billing_default_max_output_tokens", 4096))


def create_app(settings: Settings | None = None) -> FastAPI:
    configured_engine = get_engine_for_url(settings.database_url) if settings is not None else None
    configured_session_factory = (
        get_session_factory_for_engine(configured_engine) if configured_engine is not None else None
    )
    configured_audit_service = (
        AuditService(
            configured_session_factory,
            body_limit_bytes=_audit_body_limit(settings),
        )
        if configured_session_factory is not None and settings is not None
        else None
    )
    configured_billing_service = (
        BillingService(
            configured_session_factory,
            default_max_output_tokens=_billing_default_max_output_tokens(settings),
        )
        if configured_session_factory is not None and settings is not None
        else None
    )

    def app_settings() -> Settings:
        return settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active_settings = app_settings()
        engine = configured_engine or get_engine_for_url(active_settings.database_url)
        try:
            validate_runtime_settings(active_settings)
            configure_logging(level=getattr(active_settings, "log_level", "INFO"))
            await verify_database(engine, require_migration_head=True)
            session_factory = configured_session_factory or get_session_factory_for_engine(engine)
            http_client_factory = HttpClientFactory(active_settings)
            scheduler = ModelSyncScheduler(
                engine=engine,
                session_factory=session_factory,
                http_client_factory=http_client_factory,
                settings=active_settings,
            )
            app.state.settings = active_settings
            app.state.engine = engine
            app.state.session_factory = session_factory
            app.state.audit_service = AuditService(
                session_factory,
                body_limit_bytes=_audit_body_limit(active_settings),
            )
            billing_service = BillingService(
                session_factory,
                default_max_output_tokens=_billing_default_max_output_tokens(active_settings),
            )
            recovery_scheduler = BillingRecoveryScheduler(
                billing_service,
                interval_seconds=getattr(active_settings, "billing_recovery_interval_seconds", 60),
            )
            app.state.billing_service = billing_service
            app.state.http_client_factory = http_client_factory
            app.state.model_sync_scheduler = scheduler
            app.state.billing_recovery_scheduler = recovery_scheduler
            scheduler_task = asyncio.create_task(
                scheduler.run(),
                name="provider-model-sync",
            )
            recovery_task = asyncio.create_task(
                recovery_scheduler.run(),
                name="billing-reservation-recovery",
            )
            try:
                yield
            finally:
                scheduler.stop()
                recovery_scheduler.stop()
                await scheduler_task
                await recovery_task
                await http_client_factory.aclose()
        finally:
            await engine.dispose()
            if getattr(app.state, "engine", None) is engine:
                app.state.engine = None

    app = FastAPI(title="Lean AI Gateway", version="0.1.0", lifespan=lifespan)
    configure_logging(level=(getattr(settings, "log_level", "INFO") if settings else "INFO"))
    if settings is not None:
        app.state.settings = settings
        app.state.engine = configured_engine
        app.state.session_factory = configured_session_factory
        app.state.audit_service = configured_audit_service
        app.state.billing_service = configured_billing_service

    @app.middleware("http")
    async def correlate_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        return await correlation_middleware(request, call_next)

    @app.middleware("http")
    async def bind_audit_service(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        audit_service = getattr(request.app.state, "audit_service", None)
        if not isinstance(audit_service, AuditService):
            return await call_next(request)
        with use_audit_service(audit_service):
            return await call_next(request)

    async def app_session() -> AsyncIterator[AsyncSession]:
        session_factory = getattr(app.state, "session_factory", configured_session_factory)
        if session_factory is None:
            raise RuntimeError("application database session factory is not initialized")
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = app_session
    app.dependency_overrides[get_settings] = app_settings
    app.add_exception_handler(
        RequestValidationError,
        sanitized_request_validation_error_handler,
    )
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(GatewayError, gateway_error_handler)
    app.add_exception_handler(SQLAlchemyError, database_error_handler)
    app.add_exception_handler(TimeoutError, timeout_error_handler)
    app.add_exception_handler(httpx.TimeoutException, timeout_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(api_keys_router)
    app.include_router(providers_router)
    app.include_router(model_sync_router)
    app.include_router(models_router)
    app.include_router(routes_router)
    app.include_router(request_logs_router)
    app.include_router(billing_router)
    app.include_router(dashboard_router)
    app.include_router(openai_gateway_router)
    app.include_router(claude_gateway_router)
    app.include_router(gemini_gateway_router)
    app.include_router(models_gateway_router)
    app.include_router(websocket_gateway_router)

    @app.get("/health", include_in_schema=False)
    async def health(request: Request) -> JSONResponse:
        engine = getattr(request.app.state, "engine", None)
        if engine is None:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "unavailable"},
            )
        if not await database_is_available(engine):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "unavailable"},
            )
        return JSONResponse(content={"status": "ok"})

    mount_console(app, Path(__file__).resolve().parents[2] / "frontend" / "dist")

    return app


app = create_app()
