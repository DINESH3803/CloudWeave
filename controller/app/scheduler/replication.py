"""Replication management: keep every chunk at the configured replication factor."""
import hashlib
import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.worker_repository import WorkerRepository
from app.scheduler.placement import LeastLoadedPlacement, PlacementStrategy
from app.services.worker_client import WorkerClient
from shared.constants import REPLICA_STATUS_STORED, WORKER_STATUS_ACTIVE
from shared.models import WorkerInfo

logger = logging.getLogger(__name__)


class ReplicationManager:
    def __init__(self, db: Session, placement: PlacementStrategy | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.placement = placement or LeastLoadedPlacement()
        self.chunks = ChunkRepository(db)
        self.workers = WorkerRepository(db)
        self.worker_client = WorkerClient(self.settings)

    def find_under_replicated(self) -> list[str]:
        """Return IDs of chunks with fewer healthy replicas than the replication factor."""
        chunks = self.chunks.find_under_replicated(self.settings.replication_factor)
        return [c.id for c in chunks]

    def replicate_chunk(self, chunk_id: str) -> None:
        """Copy a chunk from a healthy replica to a new worker."""
        chunk = self.chunks.get_chunk(chunk_id)
        if not chunk:
            return

        # Find healthy replicas on active workers
        healthy_replicas = [
            r
            for r in chunk.replicas
            if r.status == REPLICA_STATUS_STORED
            and r.worker is not None
            and r.worker.status == WORKER_STATUS_ACTIVE
        ]
        if not healthy_replicas:
            logger.warning("No healthy replica found to copy chunk %s from", chunk_id)
            return

        # Fetch data from one healthy replica
        data: bytes | None = None
        for rep in healthy_replicas:
            try:
                raw = self.worker_client.get_chunk(rep.worker.base_url, chunk_id)
                if hashlib.sha256(raw).hexdigest() == chunk.checksum:
                    data = raw
                    break
                else:
                    logger.warning("Checksum mismatch on replica %s for chunk %s", rep.worker_id, chunk_id)
            except Exception as e:
                logger.warning("Failed to fetch replica from worker %s: %s", rep.worker_id, e)

        if data is None:
            logger.error("Could not read valid chunk %s from any healthy replica", chunk_id)
            return

        # Find candidate workers that do not already store this chunk
        existing_worker_ids = {r.worker_id for r in chunk.replicas}
        active_workers = self.workers.list_by_status(WORKER_STATUS_ACTIVE)
        candidates = [
            WorkerInfo(
                worker_id=w.id,
                base_url=w.base_url,
                status=w.status,
                capacity_bytes=w.capacity_bytes,
                used_bytes=w.used_bytes,
                last_heartbeat=w.last_heartbeat,
            )
            for w in active_workers
            if w.id not in existing_worker_ids
        ]

        if not candidates:
            logger.info("No eligible worker available to receive replica of chunk %s", chunk_id)
            return

        # Pick worker using placement strategy
        chosen = self.placement.select_workers(chunk.chunk_index, candidates, 1)[0]
        try:
            self.worker_client.put_chunk(chosen.base_url, chunk_id, data)
            self.chunks.add_replica(chunk_id, chosen.worker_id, status=REPLICA_STATUS_STORED)
            w = self.workers.get(chosen.worker_id)
            if w:
                w.used_bytes = (w.used_bytes or 0) + len(data)
                self.db.commit()
            logger.info("Restored replication for chunk %s on %s", chunk_id, chosen.worker_id)
        except Exception as e:
            logger.warning("Failed to write restored replica to %s: %s", chosen.worker_id, e)

    def restore_replication(self) -> None:
        """Re-replicate all under-replicated chunks (e.g. after a worker failure)."""
        under_replicated_ids = self.find_under_replicated()
        if under_replicated_ids:
            logger.info("Detected %d under-replicated chunks; restoring replication...", len(under_replicated_ids))
        for chunk_id in under_replicated_ids:
            try:
                self.replicate_chunk(chunk_id)
            except Exception as e:
                logger.warning("Error re-replicating chunk %s: %s", chunk_id, e)
