"""
Worker Health and Identity Endpoints.
Provides basic health check and advertising information for discovery.
"""
from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["worker"])


@router.get("/health")
def health() -> dict[str, str]:
    """Check worker health status."""
    return {"status": "ok"}


@router.get("/info")
def info() -> dict[str, str]:
    """Return worker identity and advertisement URL."""
    settings = get_settings()
    return {"worker_id": settings.worker_id, "advertise_url": settings.advertise_url}
