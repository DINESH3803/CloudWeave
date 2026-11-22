"""
Local Chunk Storage Interface.
Persists chunks as individual binary files on disk.
Provides atomic writes (temp file + fsync + atomic replace) and prevents path traversal.
"""
import hashlib
import os
import uuid
from pathlib import Path

from shared.exceptions import ChunkNotFoundError
from shared.models import ChunkReport


class ChunkStore:
    """Manages physical chunk file creation, reading, deletion, and integrity verification."""

    def __init__(self, root: Path) -> None:
        """Initialize chunk store directory on disk."""
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, chunk_id: str) -> Path:
        """Resolve safe filesystem path for a chunk ID, preventing path traversal attacks."""
        clean_name = Path(chunk_id).name
        # Reject malicious IDs containing slashes or directory traversal sequences
        if clean_name != chunk_id or ".." in chunk_id or "/" in chunk_id or "\\" in chunk_id:
            raise ValueError(f"Invalid chunk ID: {chunk_id}")
        target = (self.root / clean_name).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            raise ValueError("Path traversal attempted")
        return target

    def write(self, chunk_id: str, data: bytes) -> None:
        """Atomically persist a chunk to disk using write-to-temp, fsync, and atomic rename."""
        dest = self.path_for(chunk_id)
        tmp = self.root / f".tmp_{chunk_id}_{uuid.uuid4().hex}"
        try:
            # Write bytes to temporary file and flush to disk
            with open(tmp, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            # Atomically replace destination path with temp file
            os.replace(tmp, dest)
        finally:
            # Clean up temp file in case of write failure
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def read(self, chunk_id: str) -> bytes:
        """Read and return raw binary bytes of a stored chunk."""
        path = self.path_for(chunk_id)
        if not path.is_file():
            raise ChunkNotFoundError(chunk_id)
        return path.read_bytes()

    def delete(self, chunk_id: str) -> bool:
        """Delete a chunk file from disk; returns True if deleted or False if not present."""
        path = self.path_for(chunk_id)
        if path.is_file():
            path.unlink()
            return True
        return False

    def exists(self, chunk_id: str) -> bool:
        """Check whether a chunk file currently exists on disk."""
        return self.path_for(chunk_id).is_file()

    def list_chunks(self) -> list[ChunkReport]:
        """Scan local disk and report all stored chunks with their sizes and SHA-256 hashes."""
        reports: list[ChunkReport] = []
        if not self.root.exists():
            return reports
        for entry in self.root.iterdir():
            if entry.is_file() and not entry.name.startswith("."):
                try:
                    # Read chunk file and compute hash for reconciliation
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
        """Calculate total disk space in bytes occupied by all chunk files."""
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
