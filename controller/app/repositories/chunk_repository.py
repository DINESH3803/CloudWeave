"""Data access for chunks and chunk replicas."""
from sqlalchemy.orm import Session

from app.db.models import Chunk, ChunkReplica


class ChunkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_chunk(
        self, chunk_id: str, object_id: str, chunk_index: int, size_bytes: int, checksum: str
    ) -> Chunk:
        raise NotImplementedError

    def get_chunks_for_object(self, object_id: str) -> list[Chunk]:
        raise NotImplementedError

    def add_replica(self, chunk_id: str, worker_id: str, status: str) -> ChunkReplica:
        raise NotImplementedError

    def set_replica_status(self, chunk_id: str, worker_id: str, status: str) -> None:
        raise NotImplementedError

    def get_replicas_on_worker(self, worker_id: str) -> list[ChunkReplica]:
        raise NotImplementedError

    def find_under_replicated(self, replication_factor: int) -> list[Chunk]:
        raise NotImplementedError
