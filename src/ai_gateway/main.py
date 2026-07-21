import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from ai_gateway.admin.api_keys import router as api_keys_router
from ai_gateway.admin.model_sync import router as model_sync_router
from ai_gateway.admin.models import models_router, routes_router
from ai_gateway.admin.providers import router as providers_router
from ai_gateway.admin.users import router as users_router
from ai_gateway.auth.router import router as auth_router
from ai_gateway.catalog.scheduler import ModelSyncScheduler
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.errors import sanitized_request_validation_error_handler
from ai_gateway.db.session import get_engine_for_url, get_session_factory_for_url
from ai_gateway.transport.http import HttpClientFactory


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active_settings = settings or get_settings()
        http_client_factory = HttpClientFactory(active_settings)
        scheduler = ModelSyncScheduler(
            engine=get_engine_for_url(active_settings.database_url),
            session_factory=get_session_factory_for_url(active_settings.database_url),
            http_client_factory=http_client_factory,
            settings=active_settings,
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

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
