"""
Worker Registry.

Provides higher-level cluster membership management:
- Registering workers and reconciling their local chunk inventory on startup.
- Processing periodic heartbeat updates.
- Querying all workers or only healthy active workers for scheduler placement.
"""
from sqlalchemy.orm import Session

from app.db.models import Chunk
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.worker_repository import WorkerRepository
from shared.constants import REPLICA_STATUS_STORED, WORKER_STATUS_ACTIVE
from shared.models import WorkerHeartbeat, WorkerInfo, WorkerRegistration


class WorkerRegistry:
    """Manages worker registration, heartbeats, and cluster membership queries."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.workers = WorkerRepository(db)
        self.chunks = ChunkRepository(db)

    def register(self, registration: WorkerRegistration) -> WorkerInfo:
        """
        Add or refresh a worker and reconcile its locally stored chunks with the database.
        
        Updates worker base URL, marks it active, and verifies existing chunk replicas.
        """
        # Save or update worker record in database
        worker = self.workers.upsert(registration)

        # Reconcile reported chunks with chunk replicas in database
        for report in registration.chunks:
            # Check if this chunk is known in our database
            chunk = self.db.query(Chunk).filter(Chunk.id == report.chunk_id).first()
            if chunk:
                self.chunks.add_replica(report.chunk_id, worker.id, status=REPLICA_STATUS_STORED)

        return WorkerInfo(
            worker_id=worker.id,
            base_url=worker.base_url,
            status=worker.status,
            capacity_bytes=worker.capacity_bytes,
            used_bytes=worker.used_bytes,
            last_heartbeat=worker.last_heartbeat,
        )

    def heartbeat(self, heartbeat: WorkerHeartbeat) -> None:
        """Process a heartbeat ping from a worker, updating disk usage and last seen time."""
        self.workers.record_heartbeat(heartbeat.worker_id, heartbeat.used_bytes)

    def list_workers(self) -> list[WorkerInfo]:
        """List all registered workers in the cluster regardless of status."""
        workers = self.workers.list_all()
        return [
            WorkerInfo(
                worker_id=w.id,
                base_url=w.base_url,
                status=w.status,
                capacity_bytes=w.capacity_bytes,
                used_bytes=w.used_bytes,
                last_heartbeat=w.last_heartbeat,
            )
            for w in workers
        ]

    def get_healthy_workers(self) -> list[WorkerInfo]:
        """Retrieve only active workers suitable for storing or reading chunks."""
        workers = self.workers.list_by_status(WORKER_STATUS_ACTIVE)
        return [
            WorkerInfo(
                worker_id=w.id,
                base_url=w.base_url,
                status=w.status,
                capacity_bytes=w.capacity_bytes,
                used_bytes=w.used_bytes,
                last_heartbeat=w.last_heartbeat,
            )
            for w in workers
        ]
