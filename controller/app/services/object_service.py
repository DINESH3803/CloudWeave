"""Object-level operations used by the client-facing API."""
from collections.abc import Iterator
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.db.models import StoredObject
from app.repositories.object_repository import ObjectRepository
from app.services.chunk_service import ChunkService


class ObjectService:
    def __init__(self, db: Session) -> None:
        self.objects = ObjectRepository(db)
        self.chunk_service = ChunkService(db)

    def upload(self, name: str, content_type: str | None, stream: BinaryIO) -> StoredObject:
        """Chunk the stream, store replicas, then mark the object available."""
        raise NotImplementedError

    def download(self, object_id: str) -> Iterator[bytes]:
        """Yield the object's bytes by reassembling its chunks in order."""
        raise NotImplementedError

    def get(self, object_id: str) -> StoredObject:
        raise NotImplementedError

    def list(self, offset: int = 0, limit: int = 100) -> tuple[list[StoredObject], int]:
        raise NotImplementedError

    def delete(self, object_id: str) -> None:
        """Delete chunks from workers, then remove metadata."""
        raise NotImplementedError
