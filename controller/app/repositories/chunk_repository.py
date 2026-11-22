"""
Data Access Repository for Chunks and Chunk Replicas.

Manages persistence operations for chunks and their assigned replica locations on worker nodes.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session, joinedload

from app.db.models import Chunk, ChunkReplica, StoredObject, Worker
from shared.constants import (
    OBJECT_STATUS_AVAILABLE,
    REPLICA_STATUS_STORED,
    WORKER_STATUS_ACTIVE,
)


class ChunkRepository:
    """Database operations for chunks and chunk replicas."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add_chunk(
        self, chunk_id: str, object_id: str, chunk_index: int, size_bytes: int, checksum: str
    ) -> Chunk:
        """Insert or retrieve a chunk record for an object."""
        # Check if chunk already exists
        chunk = self.db.query(Chunk).filter(Chunk.id == chunk_id).first()
        if chunk is None:
            # Create new chunk record with size and checksum
            chunk = Chunk(
                id=chunk_id,
                object_id=object_id,
                chunk_index=chunk_index,
                size_bytes=size_bytes,
                checksum=checksum,
                status="stored",
            )
            self.db.add(chunk)
            self.db.commit()
            self.db.refresh(chunk)
        return chunk

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Fetch a single chunk by ID including its replicas and worker records."""
        # Query chunk with joined replica and worker details
        return (
            self.db.query(Chunk)
            .options(joinedload(Chunk.replicas).joinedload(ChunkReplica.worker))
            .filter(Chunk.id == chunk_id)
            .first()
        )

    def get_chunks_for_object(self, object_id: str) -> list[Chunk]:
        """Fetch all chunks for an object ordered by chunk index."""
        # Query all ordered chunks belonging to the specified object
        return (
            self.db.query(Chunk)
            .options(joinedload(Chunk.replicas).joinedload(ChunkReplica.worker))
            .filter(Chunk.object_id == object_id)
            .order_by(Chunk.chunk_index)
            .all()
        )

    def add_replica(self, chunk_id: str, worker_id: str, status: str = REPLICA_STATUS_STORED) -> ChunkReplica:
        """Record or update a replica mapping between a chunk and a worker node."""
        # Check if replica mapping already exists
        replica = (
            self.db.query(ChunkReplica)
            .filter(ChunkReplica.chunk_id == chunk_id, ChunkReplica.worker_id == worker_id)
            .first()
        )
        now = datetime.now(timezone.utc)
        if replica is None:
            # Create new replica record
            replica = ChunkReplica(
                chunk_id=chunk_id,
                worker_id=worker_id,
                status=status,
                verified_at=now,
            )
            self.db.add(replica)
        else:
            # Update existing replica status and timestamp
            replica.status = status
            replica.verified_at = now
        self.db.commit()
        self.db.refresh(replica)
        return replica

    def remove_replica(self, chunk_id: str, worker_id: str) -> bool:
        """Delete a replica record when removed from a worker node."""
        # Find and delete matching replica entry
        replica = (
            self.db.query(ChunkReplica)
            .filter(ChunkReplica.chunk_id == chunk_id, ChunkReplica.worker_id == worker_id)
            .first()
        )
        if replica:
            self.db.delete(replica)
            self.db.commit()
            return True
        return False

    def set_replica_status(self, chunk_id: str, worker_id: str, status: str) -> None:
        """Update the status string of a chunk replica (e.g. stored, corrupt)."""
        # Find replica and update its status
        replica = (
            self.db.query(ChunkReplica)
            .filter(ChunkReplica.chunk_id == chunk_id, ChunkReplica.worker_id == worker_id)
            .first()
        )
        if replica:
            replica.status = status
            self.db.commit()

    def get_replicas_on_worker(self, worker_id: str) -> list[ChunkReplica]:
        """Fetch all chunk replicas assigned to a specific worker."""
        # Query all replicas hosted on the specified worker
        return (
            self.db.query(ChunkReplica)
            .filter(ChunkReplica.worker_id == worker_id)
            .all()
        )

    def find_under_replicated(self, replication_factor: int = 2) -> list[Chunk]:
        """Find chunks of available objects that have fewer than required healthy replicas."""
        # Query all available chunks and their replicas
        chunks = (
            self.db.query(Chunk)
            .join(StoredObject, Chunk.object_id == StoredObject.id)
            .filter(StoredObject.status == OBJECT_STATUS_AVAILABLE)
            .options(joinedload(Chunk.replicas).joinedload(ChunkReplica.worker))
            .all()
        )
        under_replicated: list[Chunk] = []
        for ch in chunks:
            # Count healthy replicas located on active workers
            healthy_count = sum(
                1
                for r in ch.replicas
                if r.status == REPLICA_STATUS_STORED
                and r.worker is not None
                and r.worker.status == WORKER_STATUS_ACTIVE
            )
            # If below replication target, mark for re-replication
            if healthy_count < replication_factor:
                under_replicated.append(ch)
        return under_replicated
