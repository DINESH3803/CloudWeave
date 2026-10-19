"""Local chunk storage interface. Chunks are stored as files on persistent disk."""
from pathlib import Path

from shared.models import ChunkReport


class ChunkStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, chunk_id: str) -> Path:
        """Filesystem path of a chunk (must reject IDs that could escape `root`)."""
        raise NotImplementedError

    def write(self, chunk_id: str, data: bytes) -> None:
        """Atomically persist a chunk (write temp file, fsync, rename)."""
        raise NotImplementedError

    def read(self, chunk_id: str) -> bytes:
        raise NotImplementedError

    def delete(self, chunk_id: str) -> bool:
        """Delete a chunk; return False if it did not exist."""
        raise NotImplementedError

    def exists(self, chunk_id: str) -> bool:
        raise NotImplementedError

    def list_chunks(self) -> list[ChunkReport]:
        """Describe every stored chunk (used for registration / reconciliation)."""
        raise NotImplementedError

    def used_bytes(self) -> int:
        raise NotImplementedError
