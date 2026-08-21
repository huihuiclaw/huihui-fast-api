"""Top-level API router aggregation."""

from fastapi import APIRouter

from app.api import admob, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(admob.router)


@api_router.get("/", tags=["root"])
async def root() -> dict:
    """Root endpoint — friendly hello."""
    return {"message": "huihui-fast-api is running"}