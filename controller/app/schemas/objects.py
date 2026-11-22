"""
Pydantic Schemas for Object APIs.

Defines serialized response models for objects and paginated object lists.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ObjectOut(BaseModel):
    """
    Public response representation of a stored object.
    
    Includes object identity, size, composite SHA-256 checksum, chunk count,
    custom metadata dictionary, and creation/update timestamps.
    """
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
    """
    Paginated list response containing object summaries and total count.
    """
    items: list[ObjectOut]
    total: int
