"""Data access for objects. All object-table queries live here."""
from sqlalchemy.orm import Session

from app.db.models import StoredObject


class ObjectRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, name: str, content_type: str | None) -> StoredObject:
        raise NotImplementedError

    def get(self, object_id: str) -> StoredObject | None:
        raise NotImplementedError

    def list(self, offset: int = 0, limit: int = 100) -> tuple[list[StoredObject], int]:
        raise NotImplementedError

    def update_status(self, object_id: str, status: str) -> None:
        raise NotImplementedError

    def delete(self, object_id: str) -> None:
        raise NotImplementedError
