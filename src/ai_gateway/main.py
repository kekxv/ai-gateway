from fastapi import FastAPI

from ai_gateway.auth.router import router as auth_router


def create_app() -> FastAPI:
    app = FastAPI(title="Lean AI Gateway", version="0.1.0")
    app.include_router(auth_router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
