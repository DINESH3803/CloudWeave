"""Request/response schemas for the object APIs."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ObjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    content_type: str | None = None
    size_bytes: int
    checksum: str | None = None
    chunk_count: int
    status: str
    custom_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None


class ObjectListOut(BaseModel):
    items: list[ObjectOut]
    total: int
