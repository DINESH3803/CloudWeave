"""Python client for the CloudWeave controller REST API."""
from pathlib import Path

import httpx


class CloudWeaveClient:
    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    def upload(self, path: Path) -> dict:
        raise NotImplementedError

    def download(self, object_id: str, destination: Path) -> None:
        raise NotImplementedError

    def list_objects(self) -> list[dict]:
        raise NotImplementedError

    def metadata(self, object_id: str) -> dict:
        raise NotImplementedError

    def delete(self, object_id: str) -> None:
        raise NotImplementedError

    def cluster_status(self) -> dict:
        raise NotImplementedError

    def close(self) -> None:
        self._http.close()
