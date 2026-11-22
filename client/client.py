"""
Python Client SDK for CloudWeave Controller REST API.
Provides an easy programmatic interface for uploading, downloading,
inspecting metadata, updating custom metadata, and querying cluster health.
"""
import json
from pathlib import Path
from typing import Any
import httpx


class CloudWeaveClient:
    """Client for interacting with CloudWeave controller REST endpoints."""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 60.0) -> None:
        """Initialize HTTP client with base controller URL and request timeout."""
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    def upload(self, path: Path | str, metadata: dict[str, Any] | None = None) -> dict:
        """Upload a local file to the object store with optional custom metadata."""
        path = Path(path)
        # Check that the specified file exists locally
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        # Serialize custom metadata into JSON string form data if provided
        data = {}
        if metadata:
            data["metadata"] = json.dumps(metadata)

        # Send multipart POST request to upload object
        with open(path, "rb") as f:
            files = {"file": (path.name, f, "application/octet-stream")}
            resp = self._http.post("/api/v1/objects", files=files, data=data)
            resp.raise_for_status()
            return resp.json()

    def download(self, object_id: str, destination: Path | str | None = None) -> bytes:
        """Download an object's content and optionally write it to a destination path."""
        # Request object binary data stream from controller
        resp = self._http.get(f"/api/v1/objects/{object_id}")
        resp.raise_for_status()
        content = resp.content

        # Save downloaded bytes to destination if specified
        if destination:
            dest_path = Path(destination)
            if dest_path.is_dir():
                filename = "downloaded_file"
                cd = resp.headers.get("content-disposition", "")
                if 'filename="' in cd:
                    filename = cd.split('filename="')[1].split('"')[0]
                dest_path = dest_path / filename
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(content)
        return content

    def list_objects(self, offset: int = 0, limit: int = 100) -> dict:
        """Fetch a paginated list of stored objects from the cluster."""
        resp = self._http.get(f"/api/v1/objects?offset={offset}&limit={limit}")
        resp.raise_for_status()
        return resp.json()

    def metadata(self, object_id: str) -> dict:
        """Retrieve full metadata for an object including chunks and replica locations."""
        resp = self._http.get(f"/api/v1/objects/{object_id}/metadata")
        resp.raise_for_status()
        return resp.json()

    def patch_metadata(self, object_id: str, custom_metadata: dict[str, Any]) -> dict:
        """Update or merge custom metadata keys without re-uploading the file."""
        resp = self._http.patch(
            f"/api/v1/objects/{object_id}/metadata",
            json={"custom_metadata": custom_metadata},
        )
        resp.raise_for_status()
        return resp.json()

    def delete(self, object_id: str) -> bool:
        """Delete an object and its chunk replicas from all worker nodes."""
        resp = self._http.delete(f"/api/v1/objects/{object_id}")
        if resp.status_code == 204:
            return True
        resp.raise_for_status()
        return True

    def cluster_status(self) -> dict:
        """Query cluster health, registered workers, and storage configuration."""
        resp = self._http.get("/api/v1/cluster")
        if resp.status_code == 404:
            resp = self._http.get("/metadata/cluster")
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        """Close the underlying HTTP client connection pool."""
        self._http.close()
