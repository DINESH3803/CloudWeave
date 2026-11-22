"""
Internal Endpoints for Worker Nodes.

Called by workers during startup and periodic operation:
- Registration: Workers register their ID and base URL.
- Heartbeats: Workers send periodic health and disk usage reports.
- Chunk Inventory: Workers query which chunks they are assigned to store.
All endpoints require the internal secret token in the X-Internal-Token header.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.cluster.registry import WorkerRegistry
from app.core.config import get_settings
from app.db.models import Chunk, ChunkReplica
from app.db.session import get_db
from app.schemas.workers import WorkerHeartbeat, WorkerInfo, WorkerRegistration
from shared.constants import INTERNAL_API_PREFIX, INTERNAL_TOKEN_HEADER, REPLICA_STATUS_STORED
from shared.models import ChunkReport


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias=INTERNAL_TOKEN_HEADER),
) -> None:
    """
    Validate that incoming internal request contains the valid secret token.
    
    Protects worker-controller internal APIs from unauthorized external calls.
    """
    # Check if the provided header matches the configured internal API token
    if x_internal_token != get_settings().internal_api_token:
        raise HTTPException(status_code=401, detail="Invalid internal token")


router = APIRouter(
    prefix=f"{INTERNAL_API_PREFIX}/workers",
    tags=["internal-workers"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/register", response_model=WorkerInfo)
def register_worker(registration: WorkerRegistration, db: Session = Depends(get_db)):
    """
    Register a worker node with the controller.
    
    Records or updates worker address, capacity, and status in the database.
    """
    # Save worker registration details in the registry
    return WorkerRegistry(db).register(registration)


@router.post("/heartbeat", status_code=204)
def worker_heartbeat(heartbeat: WorkerHeartbeat, db: Session = Depends(get_db)):
    """
    Process periodic heartbeat ping from a worker node.
    
    Updates the worker's last_heartbeat timestamp and used disk bytes.
    """
    # Update heartbeat timestamp and disk usage in DB
    WorkerRegistry(db).heartbeat(heartbeat)


@router.get("", response_model=list[WorkerInfo])
def list_workers(db: Session = Depends(get_db)):
    """
    List all registered workers in the cluster.
    
    Returns current status, base URL, and disk usage for each worker node.
    """
    # Retrieve all worker entries from the database
    return WorkerRegistry(db).list_workers()


@router.get("/{worker_id}/chunks", response_model=list[ChunkReport])
def get_worker_chunks(worker_id: str, db: Session = Depends(get_db)):
    """
    Retrieve the list of chunks assigned to a specific worker.
    
    Used by workers during startup reconciliation to verify stored chunks.
    """
    # Query database for all active chunk replicas stored on this worker
    replicas = (
        db.query(ChunkReplica)
        .join(Chunk, ChunkReplica.chunk_id == Chunk.id)
        .filter(ChunkReplica.worker_id == worker_id, ChunkReplica.status == REPLICA_STATUS_STORED)
        .all()
    )
    # Return structured chunk report with size and checksum
    return [
        ChunkReport(
            chunk_id=r.chunk_id,
            size_bytes=r.chunk.size_bytes,
            checksum=r.chunk.checksum,
        )
        for r in replicas
        if r.chunk
    ]
