"""Controller configuration, loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.constants import CHUNK_SIZE_BYTES, REPLICATION_FACTOR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_name: str = "CloudWeave Controller"
    log_level: str = "INFO"

    # Metadata database (PostgreSQL)
    database_url: str = "postgresql+psycopg2://cloudweave:change-me@localhost:5432/cloudweave"

    # Storage parameters
    chunk_size_bytes: int = CHUNK_SIZE_BYTES
    replication_factor: int = REPLICATION_FACTOR

    # Cluster health
    heartbeat_timeout_seconds: int = 15
    health_check_interval_seconds: int = 5
    worker_request_timeout_seconds: float = 10.0

    # Shared secret for internal controller <-> worker calls
    internal_api_token: str = "change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
