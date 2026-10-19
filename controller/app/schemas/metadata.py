"""Schemas for metadata inspection APIs."""
from pydantic import BaseModel, ConfigDict

from app.schemas.objects import ObjectOut
from shared.models import WorkerInfo


class ReplicaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    worker_id: str
    status: str


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chunk_index: int
    size_bytes: int
    checksum: str
    replicas: list[ReplicaOut] = []


class ObjectMetadataOut(ObjectOut):
    chunks: list[ChunkOut] = []


class ClusterStatusOut(BaseModel):
    workers: list[WorkerInfo]
    replication_factor: int
    chunk_size_bytes: int
