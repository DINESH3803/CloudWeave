"""
Shared Data Models for Internal HTTP Communication.
Defines Pydantic wire models exchanged between controller and workers:
worker registration, periodic heartbeats, chunk reports, and verification results.
"""
from datetime import datetime

from pydantic import BaseModel, Field

from shared.constants import WORKER_STATUS_ACTIVE


class ChunkReport(BaseModel):
    """Details of a chunk stored locally on a worker node."""
    chunk_id: str
    size_bytes: int
    checksum: str


class WorkerRegistration(BaseModel):
    """Payload sent by a worker to the controller during initial registration."""
    worker_id: str
    base_url: str = Field(description="URL the controller uses to reach this worker")
    capacity_bytes: int | None = None
    used_bytes: int = 0
    chunks: list[ChunkReport] = Field(default_factory=list)


class WorkerHeartbeat(BaseModel):
    """Payload sent periodically by a worker to maintain active status with the controller."""
    worker_id: str
    used_bytes: int = 0
    chunk_count: int = 0
    sent_at: datetime | None = None


class WorkerInfo(BaseModel):
    """Worker node description returned by controller APIs."""
    worker_id: str
    base_url: str
    status: str = WORKER_STATUS_ACTIVE
    capacity_bytes: int | None = None
    used_bytes: int = 0
    last_heartbeat: datetime | None = None


class ChunkVerifyResult(BaseModel):
    """Checksum and existence response returned by worker /verify endpoint."""
    chunk_id: str
    exists: bool
    checksum: str | None = None
    size_bytes: int | None = None
