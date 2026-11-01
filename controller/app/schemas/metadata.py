"""Schemas for metadata inspection APIs."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.objects import ObjectOut
from shared.models import WorkerInfo


class ReplicaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    worker_id: str
    status: str
    verified_at: datetime | None = None


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chunk_index: int
    size_bytes: int
    checksum: str
    status: str = "stored"
    replicas: list[ReplicaOut] = []


class ObjectMetadataOut(ObjectOut):
    chunks: list[ChunkOut] = []


class MetadataPatchRequest(BaseModel):
    custom_metadata: dict[str, Any]


class ClusterStatusOut(BaseModel):
    workers: list[WorkerInfo]
    replication_factor: int
    chunk_size_bytes: int
