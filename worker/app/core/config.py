"""Worker configuration, loaded from environment variables."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    log_level: str = "INFO"

    # Identity: unique per worker instance
    worker_id: str = "worker-local"
    # URL at which the controller can reach this worker
    advertise_url: str = "http://localhost:8001"

    # Local persistent chunk storage
    storage_dir: Path = Path("/data/chunks")
    capacity_bytes: int | None = None

    # Controller connection
    controller_url: str = "http://localhost:8000"
    internal_api_token: str = "change-me"
    heartbeat_interval_seconds: int = 5


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
