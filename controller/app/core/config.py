"""
Controller Configuration Module.

Loads and caches configuration settings from environment variables
using pydantic-settings.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.constants import CHUNK_SIZE_BYTES, REPLICATION_FACTOR


class Settings(BaseSettings):
    """Configuration parameters for the CloudWeave controller."""
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_name: str = "CloudWeave Controller"
    log_level: str = "INFO"

    # Metadata database (PostgreSQL connection string)
    database_url: str = "postgresql+psycopg2://cloudweave:change-me@localhost:5432/cloudweave"

    # Storage parameters (1 MB chunk size, replication factor of 2)
    chunk_size_bytes: int = CHUNK_SIZE_BYTES
    replication_factor: int = REPLICATION_FACTOR

    # Cluster health & failure detection timeouts (in seconds)
    heartbeat_timeout_seconds: int = 15
    health_check_interval_seconds: int = 5
    worker_request_timeout_seconds: float = 10.0

    # Shared secret header token for internal controller <-> worker communication
    internal_api_token: str = "change-me"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached singleton instance of controller Settings.
    
    Uses lru_cache to prevent re-reading environment variables on every call.
    """
    return Settings()
