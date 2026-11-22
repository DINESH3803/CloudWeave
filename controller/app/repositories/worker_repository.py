"""
Data Access Repository for Registered Workers.

Handles storing, updating, heartbeating, and retrieving worker node status in the cluster.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db.models import Worker
from shared.constants import WORKER_STATUS_ACTIVE
from shared.models import WorkerRegistration


class WorkerRepository:
    """Database operations for cluster worker nodes."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(self, registration: WorkerRegistration) -> Worker:
        """Register a new worker or update an existing worker record."""
        worker = self.get(registration.worker_id)
        now = datetime.now(timezone.utc)
        if worker is None:
            # First-time registration for this worker node
            worker = Worker(
                id=registration.worker_id,
                base_url=str(registration.base_url).rstrip("/"),
                status=WORKER_STATUS_ACTIVE,
                capacity_bytes=registration.capacity_bytes,
                used_bytes=registration.used_bytes,
                last_heartbeat=now,
            )
            self.db.add(worker)
        else:
            # Update base URL, health status, and capacity
            worker.base_url = str(registration.base_url).rstrip("/")
            worker.status = WORKER_STATUS_ACTIVE
            if registration.capacity_bytes is not None:
                worker.capacity_bytes = registration.capacity_bytes
            worker.used_bytes = registration.used_bytes
            worker.last_heartbeat = now
        self.db.commit()
        self.db.refresh(worker)
        return worker

    def get(self, worker_id: str) -> Worker | None:
        """Retrieve a worker record by its ID."""
        return self.db.query(Worker).filter(Worker.id == worker_id).first()

    def list_all(self) -> list[Worker]:
        """Retrieve all registered workers sorted by worker ID."""
        return self.db.query(Worker).order_by(Worker.id).all()

    def list_by_status(self, status: str) -> list[Worker]:
        """Retrieve workers matching a specific status (e.g., 'active', 'offline')."""
        return self.db.query(Worker).filter(Worker.status == status).order_by(Worker.id).all()

    def record_heartbeat(self, worker_id: str, used_bytes: int) -> None:
        """Update last_heartbeat timestamp, used disk space, and mark worker active."""
        worker = self.get(worker_id)
        if worker:
            worker.last_heartbeat = datetime.now(timezone.utc)
            worker.used_bytes = used_bytes
            worker.status = WORKER_STATUS_ACTIVE
            self.db.commit()

    def set_status(self, worker_id: str, status: str) -> None:
        """Update a worker's status (e.g., mark as 'offline' or 'dead')."""
        worker = self.get(worker_id)
        if worker:
            worker.status = status
            self.db.commit()
