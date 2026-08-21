"""FastAPI application entrypoint."""

import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import api_router
from app.config import get_settings

log = logging.getLogger("huihui")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks."""
    settings = get_settings()
    # Startup
    print(f"[startup] {settings.app_name} env={settings.app_env}", flush=True)
    yield
    # Shutdown
    print("[shutdown] bye", flush=True)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler: always returns a JSON body so the client
    never gets an empty response. Logs the traceback for debugging."""
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    log.error("unhandled exception on %s %s:\n%s", request.method, request.url.path, "".join(tb))
    print("UNHANDLED EXCEPTION on", request.method, request.url.path, flush=True)
    print("".join(tb), flush=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "detail": str(exc) or "(no message)",
            "path": request.url.path,
        },
    )


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
    app.add_exception_handler(Exception, _unhandled_exception_handler)
    return app


app = create_app()