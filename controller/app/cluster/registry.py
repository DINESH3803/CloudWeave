"""Registry of workers known to the controller."""
from sqlalchemy.orm import Session

from app.repositories.worker_repository import WorkerRepository
from shared.models import WorkerHeartbeat, WorkerInfo, WorkerRegistration


class WorkerRegistry:
    def __init__(self, db: Session) -> None:
        self.workers = WorkerRepository(db)

    def register(self, registration: WorkerRegistration) -> WorkerInfo:
        """Add or refresh a worker and reconcile its reported chunks."""
        raise NotImplementedError

    def heartbeat(self, heartbeat: WorkerHeartbeat) -> None:
        raise NotImplementedError

    def list_workers(self) -> list[WorkerInfo]:
        raise NotImplementedError

    def get_healthy_workers(self) -> list[WorkerInfo]:
        raise NotImplementedError
