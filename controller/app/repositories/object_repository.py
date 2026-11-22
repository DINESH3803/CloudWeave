"""
Data Access Repository for Stored Objects.

Encapsulates all database operations for objects, including creation, retrieval,
pagination, metadata patching, status updating, and deletion.
"""
from datetime import datetime, timezone
import uuid
from sqlalchemy.orm import Session, joinedload

from app.db.models import Chunk, ChunkReplica, StoredObject
from shared.constants import OBJECT_STATUS_UPLOADING


class ObjectRepository:
    """Database operations for stored objects."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        name: str,
        content_type: str | None = None,
        object_id: str | None = None,
        size_bytes: int = 0,
        checksum: str | None = None,
        chunk_count: int = 0,
        custom_metadata: dict | None = None,
        status: str = OBJECT_STATUS_UPLOADING,
    ) -> StoredObject:
        """Create a new stored object record in the database."""
        # Generate new UUID if object_id is not provided
        obj_id = object_id or str(uuid.uuid4())
        obj = StoredObject(
            id=obj_id,
            name=name,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum=checksum,
            chunk_count=chunk_count,
            custom_metadata=custom_metadata or {},
            status=status,
        )
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def get(self, object_id: str) -> StoredObject | None:
        """Fetch an object with its full chunks, replicas, and worker relations eagerly loaded."""
        # Query object with nested joined loads for chunks, replicas, and workers
        return (
            self.db.query(StoredObject)
            .options(
                joinedload(StoredObject.chunks)
                .joinedload(Chunk.replicas)
                .joinedload(ChunkReplica.worker)
            )
            .filter(StoredObject.id == object_id)
            .first()
        )

    def list(self, offset: int = 0, limit: int = 100) -> tuple[list[StoredObject], int]:
        """Fetch a paginated list of objects ordered by creation date descending."""
        query = self.db.query(StoredObject).order_by(StoredObject.created_at.desc())
        total = query.count()
        items = query.offset(offset).limit(limit).all()
        return items, total

    def update_status(self, object_id: str, status: str) -> None:
        """Update an object's operational status (e.g. available, deleted)."""
        obj = self.db.query(StoredObject).filter(StoredObject.id == object_id).first()
        if obj:
            obj.status = status
            obj.updated_at = datetime.now(timezone.utc)
            self.db.commit()

    def update_custom_metadata(self, object_id: str, custom_metadata: dict) -> StoredObject | None:
        """
        Merge custom metadata key-values into existing metadata.
        
        Setting a key's value to None removes that key from the dictionary.
        """
        obj = self.get(object_id)
        if obj is None:
            return None
        
        # Copy existing metadata and apply updates
        current = dict(obj.custom_metadata or {})
        for k, v in custom_metadata.items():
            if v is None:
                current.pop(k, None)  # Remove key if value is None
            else:
                current[k] = v       # Set or update key
                
        obj.custom_metadata = current
        obj.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, object_id: str) -> bool:
        """Delete an object record and cascade-delete its chunks and replicas."""
        obj = self.db.query(StoredObject).filter(StoredObject.id == object_id).first()
        if obj:
            self.db.delete(obj)
            self.db.commit()
            return True
        return False
