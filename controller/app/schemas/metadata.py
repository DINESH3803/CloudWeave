"""
Pydantic Schemas for Metadata and Cluster Inspection APIs.

Defines schemas for chunk replicas, chunk metadata, in-depth object metadata,
metadata patching requests, and cluster status reports.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.objects import ObjectOut
from shared.models import WorkerInfo


class ReplicaOut(BaseModel):
    """
    Information about an individual chunk replica on a specific worker.
    """
    model_config = ConfigDict(from_attributes=True)

    worker_id: str
    status: str
    verified_at: datetime | None = None


class ChunkOut(BaseModel):
    """
    Detailed information about a chunk, its index, size, checksum, and replica locations.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    chunk_index: int
    size_bytes: int
    checksum: str
    status: str = "stored"
    replicas: list[ReplicaOut] = []


class ObjectMetadataOut(ObjectOut):
    """
    Comprehensive object metadata response including full breakdown of chunks and replicas.
    """
    chunks: list[ChunkOut] = []


class MetadataPatchRequest(BaseModel):
    """
    Request payload for patching custom metadata key-value pairs on an object.
    """
    custom_metadata: dict[str, Any]


class ClusterStatusOut(BaseModel):
    """
    Overall cluster status report with worker statuses and configuration parameters.
    """
    workers: list[WorkerInfo]
    replication_factor: int
    chunk_size_bytes: int
