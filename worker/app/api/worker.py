"""Worker health and identity endpoints."""
from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["worker"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/info")
def info() -> dict[str, str]:
    settings = get_settings()
    return {"worker_id": settings.worker_id, "advertise_url": settings.advertise_url}
