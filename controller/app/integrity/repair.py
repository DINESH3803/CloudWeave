"""Integrity verification and repair of corrupt or missing replicas."""
from datetime import datetime, timezone
import hashlib
import logging
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Chunk
from app.repositories.chunk_repository import ChunkRepository
from app.services.worker_client import WorkerClient
from shared.constants import (
    REPLICA_STATUS_CORRUPT,
    REPLICA_STATUS_STORED,
    WORKER_STATUS_ACTIVE,
)

logger = logging.getLogger(__name__)


class IntegrityRepairer:
    def __init__(self, db: Session, worker_client: WorkerClient | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.chunks = ChunkRepository(db)
        self.worker_client = worker_client or WorkerClient(self.settings)

    def verify_chunk(self, chunk_id: str) -> dict[str, bool]:
        """Ask each replica's worker to verify; return {worker_id: ok}."""
        chunk = self.chunks.get_chunk(chunk_id)
        results: dict[str, bool] = {}
        if not chunk:
            return results

        now = datetime.now(timezone.utc)
        for replica in chunk.replicas:
            if not replica.worker or replica.worker.status != WORKER_STATUS_ACTIVE:
                results[replica.worker_id] = False
                continue

            res = self.worker_client.verify_chunk(replica.worker.base_url, chunk_id)
            ok = res.exists and (res.checksum == chunk.checksum)
            results[replica.worker_id] = ok
            replica.verified_at = now
            if not ok:
                replica.status = REPLICA_STATUS_CORRUPT
            else:
                replica.status = REPLICA_STATUS_STORED
        self.db.commit()
        return results

    def repair_chunk(self, chunk_id: str) -> bool:
        """Replace corrupt/missing replicas using a good replica."""
        chunk = self.chunks.get_chunk(chunk_id)
        if not chunk:
            return False

        # First find a valid replica with correct data
        valid_data: bytes | None = None
        for rep in chunk.replicas:
            if rep.worker and rep.worker.status == WORKER_STATUS_ACTIVE:
                try:
                    data = self.worker_client.get_chunk(rep.worker.base_url, chunk_id)
                    if hashlib.sha256(data).hexdigest() == chunk.checksum:
                        valid_data = data
                        break
                except Exception:
                    pass

        if valid_data is None:
            logger.error("Cannot repair chunk %s: no valid replica available", chunk_id)
            return False

        repaired_any = False
        for rep in chunk.replicas:
            if rep.status == REPLICA_STATUS_CORRUPT and rep.worker and rep.worker.status == WORKER_STATUS_ACTIVE:
                try:
                    self.worker_client.put_chunk(rep.worker.base_url, chunk_id, valid_data)
                    rep.status = REPLICA_STATUS_STORED
                    rep.verified_at = datetime.now(timezone.utc)
                    repaired_any = True
                    logger.info("Repaired corrupted chunk %s on worker %s", chunk_id, rep.worker_id)
                except Exception as e:
                    logger.warning("Failed to repair chunk %s on worker %s: %s", chunk_id, rep.worker_id, e)

        self.db.commit()
        return repaired_any

    def scan_all(self) -> None:
        """Periodic full scan used for background integrity recovery."""
        chunks = self.db.query(Chunk).all()
        for ch in chunks:
            res = self.verify_chunk(ch.id)
            if not all(res.values()):
                logger.warning("Found corrupted or missing replica for chunk %s: %s", ch.id, res)
                self.repair_chunk(ch.id)
