"""
Internal Worker HTTP Client.

Wrapper client used by the controller to communicate with internal worker APIs
(uploading chunks, fetching chunks, deleting chunks, verifying chunk checksums).
Authenticates using the shared X-Internal-Token header.
"""
import logging
import httpx

from app.core.config import Settings, get_settings
from shared.constants import INTERNAL_API_PREFIX, INTERNAL_TOKEN_HEADER
from shared.exceptions import ChunkNotFoundError, WorkerUnavailableError
from shared.models import ChunkVerifyResult

logger = logging.getLogger(__name__)


class WorkerClient:
    """HTTP client communicating with worker internal storage endpoints."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        # Initialize reusable HTTP connection pool with authentication token
        self._client = httpx.Client(
            timeout=self.settings.worker_request_timeout_seconds,
            headers={INTERNAL_TOKEN_HEADER: self.settings.internal_api_token},
        )

    def _url(self, base_url: str, path: str) -> str:
        """Construct full internal API endpoint URL for a given worker."""
        return f"{base_url.rstrip('/')}{INTERNAL_API_PREFIX}{path}"

    def put_chunk(self, base_url: str, chunk_id: str, data: bytes) -> None:
        """
        Upload raw chunk binary data to a worker node via PUT /internal/chunks/{chunk_id}.
        
        Raises WorkerUnavailableError if worker is unreachable or returns an error.
        """
        url = self._url(base_url, f"/chunks/{chunk_id}")
        try:
            resp = self._client.put(url, content=data)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Failed to PUT chunk %s to worker %s: %s", chunk_id, base_url, e)
            raise WorkerUnavailableError(f"Failed to PUT chunk {chunk_id} to {base_url}: {e}") from e

    def get_chunk(self, base_url: str, chunk_id: str) -> bytes:
        """
        Download raw chunk binary data from a worker node via GET /internal/chunks/{chunk_id}.
        
        Raises ChunkNotFoundError if not found, or WorkerUnavailableError on connection failure.
        """
        url = self._url(base_url, f"/chunks/{chunk_id}")
        try:
            resp = self._client.get(url)
            if resp.status_code == 404:
                raise ChunkNotFoundError(chunk_id)
            resp.raise_for_status()
            return resp.content
        except ChunkNotFoundError:
            raise
        except httpx.HTTPError as e:
            logger.warning("Failed to GET chunk %s from worker %s: %s", chunk_id, base_url, e)
            raise WorkerUnavailableError(f"Failed to GET chunk {chunk_id} from {base_url}: {e}") from e

    def delete_chunk(self, base_url: str, chunk_id: str) -> None:
        """
        Instruct a worker to delete a chunk file via DELETE /internal/chunks/{chunk_id}.
        """
        url = self._url(base_url, f"/chunks/{chunk_id}")
        try:
            resp = self._client.delete(url)
            if resp.status_code not in (200, 204, 404):
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Failed to DELETE chunk %s from worker %s: %s", chunk_id, base_url, e)

    def verify_chunk(self, base_url: str, chunk_id: str) -> ChunkVerifyResult:
        """
        Ask a worker to compute the SHA-256 checksum of a stored chunk.
        
        Returns ChunkVerifyResult indicating whether the chunk exists and its checksum.
        """
        url = self._url(base_url, f"/chunks/{chunk_id}/verify")
        try:
            resp = self._client.post(url)
            if resp.status_code == 404:
                return ChunkVerifyResult(chunk_id=chunk_id, exists=False)
            resp.raise_for_status()
            return ChunkVerifyResult.model_validate(resp.json())
        except Exception as e:
            logger.warning("Failed to verify chunk %s on worker %s: %s", chunk_id, base_url, e)
            return ChunkVerifyResult(chunk_id=chunk_id, exists=False)

    def close(self) -> None:
        """Close the underlying HTTP client session."""
        self._client.close()
