"""Data access for registered workers."""
from sqlalchemy.orm import Session

from app.db.models import Worker
from shared.models import WorkerRegistration


class WorkerRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(self, registration: WorkerRegistration) -> Worker:
        raise NotImplementedError

    def get(self, worker_id: str) -> Worker | None:
        raise NotImplementedError

    def list_all(self) -> list[Worker]:
        raise NotImplementedError

    def list_by_status(self, status: str) -> list[Worker]:
        raise NotImplementedError

    def record_heartbeat(self, worker_id: str, used_bytes: int) -> None:
        raise NotImplementedError

    def set_status(self, worker_id: str, status: str) -> None:
        raise NotImplementedError
