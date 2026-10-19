"""HTTP client the controller uses to talk to workers' internal APIs."""
import httpx

from app.core.config import Settings, get_settings
from shared.constants import INTERNAL_TOKEN_HEADER
from shared.models import ChunkVerifyResult


class WorkerClient:
    """Thin wrapper over the worker chunk API. One instance may serve all workers."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            timeout=self.settings.worker_request_timeout_seconds,
            headers={INTERNAL_TOKEN_HEADER: self.settings.internal_api_token},
        )

    def put_chunk(self, base_url: str, chunk_id: str, data: bytes) -> None:
        raise NotImplementedError

    def get_chunk(self, base_url: str, chunk_id: str) -> bytes:
        raise NotImplementedError

    def delete_chunk(self, base_url: str, chunk_id: str) -> None:
        raise NotImplementedError

    def verify_chunk(self, base_url: str, chunk_id: str) -> ChunkVerifyResult:
        raise NotImplementedError

    def close(self) -> None:
        self._client.close()
