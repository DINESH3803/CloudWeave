"""Request/response schemas for the object APIs."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ObjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    content_type: str | None = None
    size_bytes: int
    checksum: str | None = None
    chunk_count: int
    status: str
    created_at: datetime


class ObjectListOut(BaseModel):
    items: list[ObjectOut]
    total: int
