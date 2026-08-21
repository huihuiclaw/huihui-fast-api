"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import api_router
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks."""
    settings = get_settings()
    # Startup
    print(f"[startup] {settings.app_name} env={settings.app_env}")
    yield
    # Shutdown
    print("[shutdown] bye")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="A minimal FastAPI service in Docker.",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    return app


app = create_app()