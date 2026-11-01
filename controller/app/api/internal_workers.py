"""Internal endpoints called by workers (registration, heartbeats, chunk inventory)."""
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
    if x_internal_token != get_settings().internal_api_token:
        raise HTTPException(status_code=401, detail="Invalid internal token")


router = APIRouter(
    prefix=f"{INTERNAL_API_PREFIX}/workers",
    tags=["internal-workers"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/register", response_model=WorkerInfo)
def register_worker(registration: WorkerRegistration, db: Session = Depends(get_db)):
    return WorkerRegistry(db).register(registration)


@router.post("/heartbeat", status_code=204)
def worker_heartbeat(heartbeat: WorkerHeartbeat, db: Session = Depends(get_db)):
    WorkerRegistry(db).heartbeat(heartbeat)


@router.get("", response_model=list[WorkerInfo])
def list_workers(db: Session = Depends(get_db)):
    return WorkerRegistry(db).list_workers()


@router.get("/{worker_id}/chunks", response_model=list[ChunkReport])
def get_worker_chunks(worker_id: str, db: Session = Depends(get_db)):
    """Retrieve information about chunks stored by a worker."""
    replicas = (
        db.query(ChunkReplica)
        .join(Chunk, ChunkReplica.chunk_id == Chunk.id)
        .filter(ChunkReplica.worker_id == worker_id, ChunkReplica.status == REPLICA_STATUS_STORED)
        .all()
    )
    return [
        ChunkReport(
            chunk_id=r.chunk_id,
            size_bytes=r.chunk.size_bytes,
            checksum=r.chunk.checksum,
        )
        for r in replicas
        if r.chunk
    ]
