"""Wire-format models for the internal controller <-> worker HTTP APIs."""
from datetime import datetime

from pydantic import BaseModel, Field

from shared.constants import WORKER_STATUS_ACTIVE


class ChunkReport(BaseModel):
    """A chunk held by a worker, as reported by that worker."""

    chunk_id: str
    size_bytes: int
    checksum: str


class WorkerRegistration(BaseModel):
    """Sent by a worker to the controller on startup."""

    worker_id: str
    base_url: str = Field(description="URL the controller uses to reach this worker")
    capacity_bytes: int | None = None
    used_bytes: int = 0
    chunks: list[ChunkReport] = Field(default_factory=list)


class WorkerHeartbeat(BaseModel):
    """Sent periodically by a worker to the controller."""

    worker_id: str
    used_bytes: int = 0
    chunk_count: int = 0
    sent_at: datetime | None = None


class WorkerInfo(BaseModel):
    """Worker description as exposed by the controller."""

    worker_id: str
    base_url: str
    status: str = WORKER_STATUS_ACTIVE
    capacity_bytes: int | None = None
    used_bytes: int = 0
    last_heartbeat: datetime | None = None


class ChunkVerifyResult(BaseModel):
    """Result of a worker re-hashing a stored chunk."""

    chunk_id: str
    exists: bool
    checksum: str | None = None
    size_bytes: int | None = None
