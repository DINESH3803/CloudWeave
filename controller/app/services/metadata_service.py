"""Read-only and update views over object, chunk and cluster metadata."""
from sqlalchemy.orm import Session

from app.cluster.registry import WorkerRegistry
from app.core.config import get_settings
from app.db.models import StoredObject
from app.repositories.object_repository import ObjectRepository
from app.repositories.worker_repository import WorkerRepository
from shared.exceptions import ObjectNotFoundError
from shared.models import WorkerInfo


class MetadataService:
    def __init__(self, db: Session) -> None:
        self.settings = get_settings()
        self.objects = ObjectRepository(db)
        self.workers = WorkerRepository(db)
        self.registry = WorkerRegistry(db)

    def get_object_metadata(self, object_id: str) -> StoredObject:
        """Return the object with its chunks and replica locations."""
        obj = self.objects.get(object_id)
        if not obj:
            raise ObjectNotFoundError(object_id)
        return obj

    def patch_custom_metadata(self, object_id: str, custom_metadata: dict) -> StoredObject:
        """Update custom metadata without touching worker chunk storage."""
        obj = self.objects.update_custom_metadata(object_id, custom_metadata)
        if not obj:
            raise ObjectNotFoundError(object_id)
        return obj

    def get_cluster_workers(self) -> list[WorkerInfo]:
        return self.registry.list_workers()
