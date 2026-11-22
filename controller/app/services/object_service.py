"""
Object Service.

Handles high-level object lifecycle operations:
- Uploading binary streams: chunking into 1 MB parts, replicating across workers, saving metadata.
- Downloading objects: reassembling ordered chunks transparently with failover.
- Listing objects with pagination.
- Object deletion: cascading cleanup of chunks across worker nodes.
"""
from collections.abc import Iterator
import hashlib
import logging
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.cluster.registry import WorkerRegistry
from app.core.config import get_settings
from app.db.models import StoredObject
from app.repositories.object_repository import ObjectRepository
from app.services.chunk_service import ChunkService, split_into_chunks
from shared.constants import (
    OBJECT_STATUS_AVAILABLE,
    OBJECT_STATUS_DELETING,
    OBJECT_STATUS_UPLOADING,
)
from shared.exceptions import NoHealthyWorkersError, ObjectNotFoundError

logger = logging.getLogger(__name__)

# Precomputed SHA-256 hex digest for an empty 0-byte file
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class ObjectService:
    """Business logic for object creation, streaming, listing, and deletion."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.objects = ObjectRepository(db)
        self.chunk_service = ChunkService(db)
        self.registry = WorkerRegistry(db)

    def upload(
        self,
        name: str,
        content_type: str | None,
        stream: BinaryIO,
        custom_metadata: dict | None = None,
    ) -> StoredObject:
        """
        Split upload stream into chunks, store replicas across workers, and mark object available.
        
        Ensures atomic rollback: if upload fails midway, already-written chunks are cleaned up.
        """
        # 1. Verify enough healthy workers are available to satisfy replication factor
        healthy_workers = self.registry.get_healthy_workers()
        if len(healthy_workers) < self.settings.replication_factor:
            raise NoHealthyWorkersError(
                f"Cannot upload: only {len(healthy_workers)} healthy worker(s) online, "
                f"minimum required replication factor is {self.settings.replication_factor}"
            )

        # 2. Create the initial database record in UPLOADING status
        obj = self.objects.create(
            name=name,
            content_type=content_type or "application/octet-stream",
            status=OBJECT_STATUS_UPLOADING,
            custom_metadata=custom_metadata or {},
        )

        stored_chunk_ids: list[str] = []
        file_hasher = hashlib.sha256()
        total_size = 0
        chunk_index = 0

        try:
            # 3. Read stream in 1 MB blocks and distribute replicas across workers
            for block in split_into_chunks(stream, self.settings.chunk_size_bytes):
                file_hasher.update(block)
                total_size += len(block)
                chunk_id = self.chunk_service.store_chunk(
                    object_id=obj.id,
                    chunk_index=chunk_index,
                    data=block,
                    candidates=healthy_workers,
                )
                stored_chunk_ids.append(chunk_id)
                chunk_index += 1

            # 4. Finalize object record metadata and mark AVAILABLE
            obj.size_bytes = total_size
            obj.checksum = file_hasher.hexdigest() if chunk_index > 0 else EMPTY_SHA256
            obj.chunk_count = chunk_index
            obj.status = OBJECT_STATUS_AVAILABLE
            self.db.commit()
            self.db.refresh(obj)
            logger.info("Uploaded object %s (%s, %d bytes, %d chunks)", obj.id, obj.name, total_size, chunk_index)
            return obj

        except Exception as e:
            # Rollback: Clean up any chunks written to workers before failing
            logger.exception("Upload failed for object %s: %s; cleaning up chunks...", obj.id, e)
            for cid in stored_chunk_ids:
                try:
                    self.chunk_service.delete_chunk(cid)
                except Exception:
                    pass
            self.objects.delete(obj.id)
            raise

    def download(self, object_id: str) -> Iterator[bytes]:
        """
        Yield object byte stream by retrieving and reassembling chunks sequentially.
        
        Reads chunks in order (chunk 0, 1, 2...) transparently to the caller.
        """
        obj = self.get(object_id)
        if obj.chunk_count == 0:
            yield b""
            return

        # Stream chunks one by one
        for chunk in obj.chunks:
            yield self.chunk_service.read_chunk(chunk.id)

    def get(self, object_id: str) -> StoredObject:
        """
        Fetch object record by ID.
        
        Raises ObjectNotFoundError if the record does not exist.
        """
        obj = self.objects.get(object_id)
        if not obj:
            raise ObjectNotFoundError(object_id)
        return obj

    def list(self, offset: int = 0, limit: int = 100) -> tuple[list[StoredObject], int]:
        """Fetch a paginated list of objects and total record count."""
        return self.objects.list(offset, limit)

    def delete(self, object_id: str) -> None:
        """
        Delete an object and clean up all its chunk replicas from worker nodes.
        
        Sets status to DELETING, purges worker chunks, and removes DB record.
        """
        obj = self.get(object_id)
        # Mark object as deleting to prevent concurrent downloads
        self.objects.update_status(object_id, OBJECT_STATUS_DELETING)

        # Delete chunk files from worker nodes
        for chunk in obj.chunks:
            self.chunk_service.delete_chunk(chunk.id)

        # Remove object record from metadata database
        self.objects.delete(object_id)
        logger.info("Deleted object %s and its chunks", object_id)
