"""Object-level operations used by the client-facing API."""
from collections.abc import Iterator
import hashlib
import logging
import tempfile
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
from shared.exceptions import (
    ChecksumMismatchError,
    NoHealthyWorkersError,
    ObjectIntegrityError,
    ObjectNotFoundError,
    WorkerUnavailableError,
)

logger = logging.getLogger(__name__)

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_STREAM_BLOCK = 256 * 1024  # 256 KiB read blocks for response streaming


class ObjectService:
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
        """Chunk the stream, store replicas across workers, then mark the object available."""
        healthy_workers = self.registry.get_healthy_workers()
        if len(healthy_workers) < self.settings.replication_factor:
            raise NoHealthyWorkersError(
                f"Cannot upload: only {len(healthy_workers)} healthy worker(s) online, "
                f"minimum required replication factor is {self.settings.replication_factor}"
            )

        # Create the initial record in UPLOADING state
        obj = self.objects.create(
            name=name,
            content_type=content_type or "application/octet-stream",
            status=OBJECT_STATUS_UPLOADING,
            custom_metadata=custom_metadata or {},
        )

        stored_chunk_ids: list[str] = []
        failed_workers: set[str] = set()  # workers that failed during this upload are tried last
        file_hasher = hashlib.sha256()
        total_size = 0
        chunk_index = 0

        try:
            for block in split_into_chunks(stream, self.settings.chunk_size_bytes):
                file_hasher.update(block)
                total_size += len(block)
                chunk_id = self.chunk_service.store_chunk(
                    object_id=obj.id,
                    chunk_index=chunk_index,
                    data=block,
                    candidates=healthy_workers,
                    failed_workers=failed_workers,
                )
                stored_chunk_ids.append(chunk_id)
                chunk_index += 1

            # Complete upload record
            obj.size_bytes = total_size
            obj.checksum = file_hasher.hexdigest() if chunk_index > 0 else EMPTY_SHA256
            obj.chunk_count = chunk_index
            obj.status = OBJECT_STATUS_AVAILABLE
            self.db.commit()
            self.db.refresh(obj)
            logger.info("Uploaded object %s (%s, %d bytes, %d chunks)", obj.id, obj.name, total_size, chunk_index)
            return obj

        except Exception as e:
            logger.exception("Upload failed for object %s: %s; cleaning up chunks...", obj.id, e)
            self._cleanup_failed_upload(obj.id, stored_chunk_ids)
            raise  # always the original error; cleanup problems are only logged

    def _cleanup_failed_upload(self, object_id: str, chunk_ids: list[str]) -> None:
        """Remove what a failed upload stored. Never raises."""
        try:
            self.db.rollback()  # the failure may have left the session needing a rollback
        except Exception as e:
            logger.warning("Cleanup of failed upload %s: rollback failed: %s", object_id, type(e).__name__)
        for cid in chunk_ids:
            try:
                self.chunk_service.delete_chunk(cid)
            except Exception as e:
                logger.warning("Cleanup of failed upload %s: could not delete chunk %s: %s", object_id, cid, type(e).__name__)
        try:
            self.objects.delete(object_id)
        except Exception as e:
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(
                "Cleanup of failed upload %s: could not remove its metadata (%s); it remains in 'uploading' state",
                object_id, type(e).__name__,
            )

    def download(self, object_id: str) -> tuple[StoredObject, Iterator[bytes]]:
        """Retrieve the complete object into a spooled temp file, validate it, then return a streaming iterator.

        All retrieval and validation is completed BEFORE returning. If anything fails,
        an exception is raised here — before any HTTP response headers are sent.
        """
        obj = self.get(object_id)

        if obj.chunk_count == 0:
            # Empty object: nothing to retrieve or validate.
            return obj, iter([b""])

        # Retrieve all chunks into a spooled temporary file.
        # SpooledTemporaryFile stays in memory up to max_size, then spills to disk.
        tmp = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
        try:
            reconstructed_size = 0
            obj_hasher = hashlib.sha256()

            chunks = sorted(obj.chunks, key=lambda c: c.chunk_index)
            if len(chunks) != obj.chunk_count:
                raise ObjectIntegrityError(
                    f"Object {object_id}: expected {obj.chunk_count} chunk(s), "
                    f"found {len(chunks)} in metadata"
                )

            for chunk_meta in chunks:
                chunk_data = self.chunk_service.read_chunk(chunk_meta.id)
                # read_chunk already verifies per-chunk checksum and falls back to alternates.
                # Double-check here as a defence against bugs in read_chunk.
                computed = hashlib.sha256(chunk_data).hexdigest()
                if computed != chunk_meta.checksum:
                    raise ChecksumMismatchError(
                        f"Chunk {chunk_meta.id} checksum mismatch after retrieval"
                    )
                tmp.write(chunk_data)
                reconstructed_size += len(chunk_data)
                obj_hasher.update(chunk_data)

            # Validate reconstructed size.
            if reconstructed_size != obj.size_bytes:
                raise ObjectIntegrityError(
                    f"Object {object_id}: reconstructed size {reconstructed_size} "
                    f"does not match stored size {obj.size_bytes}"
                )

            # Validate final object checksum if present.
            if obj.checksum and obj.checksum != EMPTY_SHA256:
                final_checksum = obj_hasher.hexdigest()
                if final_checksum != obj.checksum:
                    raise ObjectIntegrityError(
                        f"Object {object_id}: final checksum mismatch"
                    )

            # All checks passed. Seek to beginning and return a streaming generator.
            tmp.seek(0)

        except Exception:
            tmp.close()
            raise

        def _stream(spooled: tempfile.SpooledTemporaryFile) -> Iterator[bytes]:  # type: ignore[type-arg]
            try:
                while True:
                    block = spooled.read(_STREAM_BLOCK)
                    if not block:
                        break
                    yield block
            finally:
                spooled.close()

        return obj, _stream(tmp)

    def get(self, object_id: str) -> StoredObject:
        obj = self.objects.get(object_id)
        if not obj:
            raise ObjectNotFoundError(object_id)
        return obj

    def list(self, offset: int = 0, limit: int = 100) -> tuple[list[StoredObject], int]:
        return self.objects.list(offset, limit)

    def delete(self, object_id: str) -> None:
        """Delete chunks from workers, then remove metadata."""
        obj = self.get(object_id)
        self.objects.update_status(object_id, OBJECT_STATUS_DELETING)

        for chunk in obj.chunks:
            self.chunk_service.delete_chunk(chunk.id)

        self.objects.delete(object_id)
        logger.info("Deleted object %s and its chunks", object_id)
