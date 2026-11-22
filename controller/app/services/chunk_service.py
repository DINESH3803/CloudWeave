"""
Chunk Service.

Handles chunk-level operations:
- Splitting binary streams into fixed 1 MB byte segments.
- Placing chunk replicas onto distinct worker nodes.
- Retrieving chunks with transparent failover and automatic corruption healing.
- Cascading deletion of chunks across worker nodes.
"""
from collections.abc import Iterator
import hashlib
import logging
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.worker_repository import WorkerRepository
from app.scheduler.placement import LeastLoadedPlacement, PlacementStrategy
from app.services.worker_client import WorkerClient
from shared.constants import (
    REPLICA_STATUS_CORRUPT,
    REPLICA_STATUS_STORED,
    WORKER_STATUS_ACTIVE,
)
from shared.exceptions import ChunkNotFoundError, WorkerUnavailableError
from shared.models import WorkerInfo

logger = logging.getLogger(__name__)


def split_into_chunks(stream: BinaryIO, chunk_size: int) -> Iterator[bytes]:
    """
    Read binary stream in successive blocks of size `chunk_size` (1 MB).
    
    The final chunk block may be smaller than chunk_size.
    """
    while block := stream.read(chunk_size):
        yield block


class ChunkService:
    """Manages chunk storage, replica placement, retrieval, and auto-repair."""

    def __init__(
        self,
        db: Session,
        worker_client: WorkerClient | None = None,
        placement: PlacementStrategy | None = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()
        self.chunks = ChunkRepository(db)
        self.workers = WorkerRepository(db)
        self.worker_client = worker_client or WorkerClient(self.settings)
        self.placement = placement or LeastLoadedPlacement()

    def store_chunk(
        self,
        object_id: str,
        chunk_index: int,
        data: bytes,
        candidates: list[WorkerInfo],
    ) -> str:
        """
        Compute checksum, select worker nodes, write replicas, and record chunk in database.
        
        Uses the placement strategy to select distinct workers maintaining replication factor 2.
        """
        # 1. Format deterministic chunk ID and compute SHA-256 checksum
        chunk_id = f"{object_id}_{chunk_index}"
        checksum = hashlib.sha256(data).hexdigest()

        # 2. Select distinct workers based on least load
        selected_workers = self.placement.select_workers(
            chunk_index=chunk_index,
            candidates=candidates,
            count=self.settings.replication_factor,
        )

        # 3. Transmit chunk bytes to selected worker nodes
        for worker in selected_workers:
            self.worker_client.put_chunk(worker.base_url, chunk_id, data)

        # 4. Save chunk metadata record in database
        self.chunks.add_chunk(
            chunk_id=chunk_id,
            object_id=object_id,
            chunk_index=chunk_index,
            size_bytes=len(data),
            checksum=checksum,
        )

        # 5. Save replica mappings and update disk usage accounting
        for worker in selected_workers:
            self.chunks.add_replica(chunk_id, worker.worker_id, status=REPLICA_STATUS_STORED)
            worker.used_bytes += len(data)
            w = self.workers.get(worker.worker_id)
            if w:
                w.used_bytes = (w.used_bytes or 0) + len(data)

        self.db.commit()
        return chunk_id

    def read_chunk(self, chunk_id: str) -> bytes:
        """
        Retrieve chunk data from a healthy replica with failover and auto-repair.
        
        Validates SHA-256 checksum. If corrupted, falls back to another replica
        and repairs the damaged replica using the valid data.
        """
        chunk = self.chunks.get_chunk(chunk_id)
        if not chunk:
            raise ChunkNotFoundError(chunk_id)

        # Prioritize replicas on active workers
        sorted_replicas = sorted(
            chunk.replicas,
            key=lambda r: 0 if (r.worker and r.worker.status == WORKER_STATUS_ACTIVE) else 1,
        )

        valid_data: bytes | None = None
        corrupted_replicas = []

        # Attempt to read from each replica until a checksum-verified copy is obtained
        for replica in sorted_replicas:
            if not replica.worker:
                continue
            try:
                raw = self.worker_client.get_chunk(replica.worker.base_url, chunk_id)
                computed = hashlib.sha256(raw).hexdigest()
                # Verify chunk integrity against stored checksum
                if computed == chunk.checksum:
                    valid_data = raw
                    break
                else:
                    # Corruption detected: mark replica and continue to next replica
                    logger.warning(
                        "Data corruption detected on worker %s for chunk %s (checksum mismatch)",
                        replica.worker_id,
                        chunk_id,
                    )
                    replica.status = REPLICA_STATUS_CORRUPT
                    corrupted_replicas.append(replica)
                    self.db.commit()
            except Exception as e:
                # Worker offline or unreachable: fall back to next replica
                logger.warning("Failed to fetch chunk %s from %s: %s", chunk_id, replica.worker_id, e)

        # If all replicas failed or were corrupted, raise 503
        if valid_data is None:
            raise WorkerUnavailableError(f"No accessible and uncorrupted replica for chunk {chunk_id}")

        # Auto-repair: restore valid data onto any replica that had corruption
        for corrupt_rep in corrupted_replicas:
            if corrupt_rep.worker and corrupt_rep.worker.status == WORKER_STATUS_ACTIVE:
                try:
                    logger.info("Auto-repairing corrupted replica on %s...", corrupt_rep.worker_id)
                    self.worker_client.put_chunk(corrupt_rep.worker.base_url, chunk_id, valid_data)
                    corrupt_rep.status = REPLICA_STATUS_STORED
                    self.db.commit()
                    logger.info("Successfully repaired replica on %s", corrupt_rep.worker_id)
                except Exception as ex:
                    logger.warning("Failed to auto-repair corrupt replica on %s: %s", corrupt_rep.worker_id, ex)

        return valid_data

    def delete_chunk(self, chunk_id: str) -> None:
        """Instruct all workers holding a replica of this chunk to delete their chunk file."""
        chunk = self.chunks.get_chunk(chunk_id)
        if not chunk:
            return
        # Remove replica files from each worker node
        for replica in chunk.replicas:
            if replica.worker:
                try:
                    self.worker_client.delete_chunk(replica.worker.base_url, chunk_id)
                except Exception as e:
                    logger.warning("Failed to delete chunk %s on %s: %s", chunk_id, replica.worker_id, e)
