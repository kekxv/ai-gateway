import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.admin.api_keys import router as api_keys_router
from ai_gateway.admin.billing import router as billing_router
from ai_gateway.admin.model_sync import router as model_sync_router
from ai_gateway.admin.models import models_router, routes_router
from ai_gateway.admin.providers import router as providers_router
from ai_gateway.admin.request_logs import router as request_logs_router
from ai_gateway.admin.users import router as users_router
from ai_gateway.audit.codec import DEFAULT_AUDIT_BODY_LIMIT_BYTES
from ai_gateway.audit.service import AuditService, use_audit_service
from ai_gateway.auth.router import router as auth_router
from ai_gateway.billing.service import BillingService
from ai_gateway.catalog.scheduler import ModelSyncScheduler
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.errors import sanitized_request_validation_error_handler
from ai_gateway.db.session import get_engine_for_url, get_session, get_session_factory_for_url
from ai_gateway.gateway.claude import router as claude_gateway_router
from ai_gateway.gateway.gemini import router as gemini_gateway_router
from ai_gateway.gateway.openai import router as openai_gateway_router
from ai_gateway.transport.http import HttpClientFactory


def _audit_body_limit(settings: object) -> int:
    return int(getattr(settings, "audit_body_limit_bytes", DEFAULT_AUDIT_BODY_LIMIT_BYTES))


def _billing_default_max_output_tokens(settings: object) -> int:
    return int(getattr(settings, "billing_default_max_output_tokens", 4096))


def create_app(settings: Settings | None = None) -> FastAPI:
    configured_engine = get_engine_for_url(settings.database_url) if settings is not None else None
    configured_session_factory = (
        get_session_factory_for_url(settings.database_url) if settings is not None else None
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
        session_factory = configured_session_factory or get_session_factory_for_url(
            active_settings.database_url
        )
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
        app.state.billing_service = BillingService(
            session_factory,
            default_max_output_tokens=_billing_default_max_output_tokens(active_settings),
        )
        app.state.http_client_factory = http_client_factory
        app.state.model_sync_scheduler = scheduler
        scheduler_task = asyncio.create_task(
            scheduler.run(),
            name="provider-model-sync",
        )
        try:
            yield
        finally:
            scheduler.stop()
            await scheduler_task
            await http_client_factory.aclose()

    app = FastAPI(title="Lean AI Gateway", version="0.1.0", lifespan=lifespan)
    if settings is not None:
        app.state.settings = settings
        app.state.engine = configured_engine
        app.state.session_factory = configured_session_factory
        app.state.audit_service = configured_audit_service
        app.state.billing_service = configured_billing_service

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
        active_settings = app_settings()
        session_factory = configured_session_factory or get_session_factory_for_url(
            active_settings.database_url
        )
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = app_session
    app.dependency_overrides[get_settings] = app_settings
    app.add_exception_handler(
        RequestValidationError,
        sanitized_request_validation_error_handler,
    )
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(api_keys_router)
    app.include_router(providers_router)
    app.include_router(model_sync_router)
    app.include_router(models_router)
    app.include_router(routes_router)
    app.include_router(request_logs_router)
    app.include_router(billing_router)
    app.include_router(openai_gateway_router)
    app.include_router(claude_gateway_router)
    app.include_router(gemini_gateway_router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
