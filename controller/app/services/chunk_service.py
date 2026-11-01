"""Chunk-level operations: splitting data, placing and fetching chunks."""
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
    """Yield successive chunk_size blocks from a binary stream (last may be shorter)."""
    while block := stream.read(chunk_size):
        yield block


class ChunkService:
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
        """Checksum, choose workers, write replicas, record metadata."""
        chunk_id = f"{object_id}_{chunk_index}"
        checksum = hashlib.sha256(data).hexdigest()

        selected_workers = self.placement.select_workers(
            chunk_index=chunk_index,
            candidates=candidates,
            count=self.settings.replication_factor,
        )

        for worker in selected_workers:
            self.worker_client.put_chunk(worker.base_url, chunk_id, data)

        self.chunks.add_chunk(
            chunk_id=chunk_id,
            object_id=object_id,
            chunk_index=chunk_index,
            size_bytes=len(data),
            checksum=checksum,
        )

        for worker in selected_workers:
            self.chunks.add_replica(chunk_id, worker.worker_id, status=REPLICA_STATUS_STORED)
            # Update candidate used_bytes locally and in DB
            worker.used_bytes += len(data)
            w = self.workers.get(worker.worker_id)
            if w:
                w.used_bytes = (w.used_bytes or 0) + len(data)

        self.db.commit()
        return chunk_id

    def read_chunk(self, chunk_id: str) -> bytes:
        """Fetch from a healthy replica, verify checksum, fall back to another replica."""
        chunk = self.chunks.get_chunk(chunk_id)
        if not chunk:
            raise ChunkNotFoundError(chunk_id)

        # Order replicas to prioritize active workers
        sorted_replicas = sorted(
            chunk.replicas,
            key=lambda r: 0 if (r.worker and r.worker.status == WORKER_STATUS_ACTIVE) else 1,
        )

        valid_data: bytes | None = None
        corrupted_replicas = []

        for replica in sorted_replicas:
            if not replica.worker:
                continue
            try:
                raw = self.worker_client.get_chunk(replica.worker.base_url, chunk_id)
                computed = hashlib.sha256(raw).hexdigest()
                if computed == chunk.checksum:
                    valid_data = raw
                    break
                else:
                    logger.warning(
                        "Data corruption detected on worker %s for chunk %s (checksum mismatch)",
                        replica.worker_id,
                        chunk_id,
                    )
                    replica.status = REPLICA_STATUS_CORRUPT
                    corrupted_replicas.append(replica)
                    self.db.commit()
            except Exception as e:
                logger.warning("Failed to fetch chunk %s from %s: %s", chunk_id, replica.worker_id, e)

        if valid_data is None:
            raise WorkerUnavailableError(f"No accessible and uncorrupted replica for chunk {chunk_id}")

        # If any replica was corrupted, auto-repair it in background/inline using valid_data!
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
        """Remove every replica of the chunk from workers."""
        chunk = self.chunks.get_chunk(chunk_id)
        if not chunk:
            return
        for replica in chunk.replicas:
            if replica.worker:
                try:
                    self.worker_client.delete_chunk(replica.worker.base_url, chunk_id)
                except Exception as e:
                    logger.warning("Failed to delete chunk %s on %s: %s", chunk_id, replica.worker_id, e)
