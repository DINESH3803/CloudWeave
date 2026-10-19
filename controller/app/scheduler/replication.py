"""Replication management: keep every chunk at the configured replication factor."""
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.scheduler.placement import LeastLoadedPlacement, PlacementStrategy


class ReplicationManager:
    def __init__(self, db: Session, placement: PlacementStrategy | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.placement = placement or LeastLoadedPlacement()

    def find_under_replicated(self) -> list[str]:
        """Return IDs of chunks with fewer healthy replicas than the replication factor."""
        raise NotImplementedError

    def replicate_chunk(self, chunk_id: str) -> None:
        """Copy a chunk from a healthy replica to a new worker."""
        raise NotImplementedError

    def restore_replication(self) -> None:
        """Re-replicate all under-replicated chunks (e.g. after a worker failure)."""
        raise NotImplementedError
