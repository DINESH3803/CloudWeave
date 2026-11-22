"""
Worker Configuration Module.
Loads node identity, storage path, controller URL, and heartbeat intervals
from environment variables via pydantic-settings.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Configuration settings for a storage worker instance."""
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    log_level: str = "INFO"

    # Worker unique identity and network advertisement address
    worker_id: str = "worker-local"
    advertise_url: str = "http://localhost:8001"

    # Local disk path for storing 1 MB chunk files
    storage_dir: Path = Path("/data/chunks")
    capacity_bytes: int | None = None

    # Controller connection and heartbeat configuration
    controller_url: str = "http://localhost:8000"
    internal_api_token: str = "change-me"
    heartbeat_interval_seconds: int = 5


@lru_cache
def get_settings() -> WorkerSettings:
    """Retrieve cached singleton worker settings."""
    return WorkerSettings()
