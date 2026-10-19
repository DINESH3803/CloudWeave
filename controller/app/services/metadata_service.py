"""Read-only views over object, chunk and cluster metadata."""
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import StoredObject
from app.repositories.object_repository import ObjectRepository
from app.repositories.worker_repository import WorkerRepository
from shared.models import WorkerInfo


class MetadataService:
    def __init__(self, db: Session) -> None:
        self.settings = get_settings()
        self.objects = ObjectRepository(db)
        self.workers = WorkerRepository(db)

    def get_object_metadata(self, object_id: str) -> StoredObject:
        """Return the object with its chunks and replica locations."""
        raise NotImplementedError

    def get_cluster_workers(self) -> list[WorkerInfo]:
        raise NotImplementedError
