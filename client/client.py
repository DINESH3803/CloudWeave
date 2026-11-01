"""Python client for the CloudWeave controller REST API."""
import json
from pathlib import Path
from typing import Any
import httpx


class CloudWeaveClient:
    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    def upload(self, path: Path | str, metadata: dict[str, Any] | None = None) -> dict:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        data = {}
        if metadata:
            data["metadata"] = json.dumps(metadata)

        with open(path, "rb") as f:
            files = {"file": (path.name, f, "application/octet-stream")}
            resp = self._http.post("/api/v1/objects", files=files, data=data)
            resp.raise_for_status()
            return resp.json()

    def download(self, object_id: str, destination: Path | str | None = None) -> bytes:
        resp = self._http.get(f"/api/v1/objects/{object_id}")
        resp.raise_for_status()
        content = resp.content
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
        resp = self._http.get(f"/api/v1/objects?offset={offset}&limit={limit}")
        resp.raise_for_status()
        return resp.json()

    def metadata(self, object_id: str) -> dict:
        resp = self._http.get(f"/api/v1/objects/{object_id}/metadata")
        resp.raise_for_status()
        return resp.json()

    def patch_metadata(self, object_id: str, custom_metadata: dict[str, Any]) -> dict:
        resp = self._http.patch(
            f"/api/v1/objects/{object_id}/metadata",
            json={"custom_metadata": custom_metadata},
        )
        resp.raise_for_status()
        return resp.json()

    def delete(self, object_id: str) -> bool:
        resp = self._http.delete(f"/api/v1/objects/{object_id}")
        if resp.status_code == 204:
            return True
        resp.raise_for_status()
        return True

    def cluster_status(self) -> dict:
        resp = self._http.get("/api/v1/cluster")
        if resp.status_code == 404:
            resp = self._http.get("/metadata/cluster")
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._http.close()
