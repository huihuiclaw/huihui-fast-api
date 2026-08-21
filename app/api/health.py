"""Health check endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — returns 200 OK if the process is running."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def ready() -> dict:
    """Readiness probe — extend with real dependency checks as needed."""
    settings = get_settings()
    return {
        "status": "ready",
        "app": settings.app_name,
        "env": settings.app_env,
    }