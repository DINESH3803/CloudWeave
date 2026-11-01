"""Local chunk storage interface. Chunks are stored as files on persistent disk."""
import hashlib
import os
import uuid
from pathlib import Path

from shared.exceptions import ChunkNotFoundError
from shared.models import ChunkReport


class ChunkStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, chunk_id: str) -> Path:
        """Filesystem path of a chunk (must reject IDs that could escape `root`)."""
        clean_name = Path(chunk_id).name
        if clean_name != chunk_id or ".." in chunk_id or "/" in chunk_id or "\\" in chunk_id:
            raise ValueError(f"Invalid chunk ID: {chunk_id}")
        target = (self.root / clean_name).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            raise ValueError("Path traversal attempted")
        return target

    def write(self, chunk_id: str, data: bytes) -> None:
        """Atomically persist a chunk (write temp file, fsync, rename)."""
        dest = self.path_for(chunk_id)
        tmp = self.root / f".tmp_{chunk_id}_{uuid.uuid4().hex}"
        try:
            with open(tmp, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def read(self, chunk_id: str) -> bytes:
        path = self.path_for(chunk_id)
        if not path.is_file():
            raise ChunkNotFoundError(chunk_id)
        return path.read_bytes()

    def delete(self, chunk_id: str) -> bool:
        """Delete a chunk; return False if it did not exist."""
        path = self.path_for(chunk_id)
        if path.is_file():
            path.unlink()
            return True
        return False

    def exists(self, chunk_id: str) -> bool:
        return self.path_for(chunk_id).is_file()

    def list_chunks(self) -> list[ChunkReport]:
        """Describe every stored chunk (used for registration / reconciliation)."""
        reports: list[ChunkReport] = []
        if not self.root.exists():
            return reports
        for entry in self.root.iterdir():
            if entry.is_file() and not entry.name.startswith("."):
                try:
                    data = entry.read_bytes()
                    checksum = hashlib.sha256(data).hexdigest()
                    reports.append(
                        ChunkReport(
                            chunk_id=entry.name,
                            size_bytes=len(data),
                            checksum=checksum,
                        )
                    )
                except OSError:
                    continue
        return reports

    def used_bytes(self) -> int:
        total = 0
        if not self.root.exists():
            return total
        for entry in self.root.iterdir():
            if entry.is_file() and not entry.name.startswith("."):
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
        return total
