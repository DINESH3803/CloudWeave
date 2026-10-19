"""Chunk-level operations: splitting data, placing and fetching chunks."""
from collections.abc import Iterator
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.worker_repository import WorkerRepository
from app.services.worker_client import WorkerClient


def split_into_chunks(stream: BinaryIO, chunk_size: int) -> Iterator[bytes]:
    """Yield successive chunk_size blocks from a binary stream (last may be shorter)."""
    while block := stream.read(chunk_size):
        yield block


class ChunkService:
    def __init__(self, db: Session, worker_client: WorkerClient | None = None) -> None:
        self.settings = get_settings()
        self.chunks = ChunkRepository(db)
        self.workers = WorkerRepository(db)
        self.worker_client = worker_client or WorkerClient(self.settings)

    def store_chunk(self, object_id: str, chunk_index: int, data: bytes) -> None:
        """Checksum, choose workers, write replicas, record metadata."""
        raise NotImplementedError

    def read_chunk(self, chunk_id: str) -> bytes:
        """Fetch from a healthy replica, verify checksum, fall back to another replica."""
        raise NotImplementedError

    def delete_chunk(self, chunk_id: str) -> None:
        """Remove every replica of the chunk from workers."""
        raise NotImplementedError
