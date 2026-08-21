"""Top-level API router aggregation."""

from fastapi import APIRouter

from app.api import health

api_router = APIRouter()
api_router.include_router(health.router)


@api_router.get("/", tags=["root"])
async def root() -> dict:
    """Root endpoint — friendly hello."""
    return {"message": "huihui-fast-api is running"}