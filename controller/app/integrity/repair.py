"""Integrity verification and repair of corrupt or missing replicas."""
from sqlalchemy.orm import Session

from app.services.worker_client import WorkerClient


class IntegrityRepairer:
    def __init__(self, db: Session, worker_client: WorkerClient | None = None) -> None:
        self.db = db
        self.worker_client = worker_client or WorkerClient()

    def verify_chunk(self, chunk_id: str) -> dict[str, bool]:
        """Ask each replica's worker to verify; return {worker_id: ok}."""
        raise NotImplementedError

    def repair_chunk(self, chunk_id: str) -> None:
        """Replace corrupt/missing replicas using a good replica."""
        raise NotImplementedError

    def scan_all(self) -> None:
        """Periodic full scan used for background integrity recovery."""
        raise NotImplementedError
