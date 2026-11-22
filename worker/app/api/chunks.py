"""
Internal Chunk Storage Endpoints for Worker Nodes.
Called exclusively by the controller for uploading, downloading,
deleting, and verifying checksum integrity of stored chunks.
Requires X-Internal-Token header for authorization.
"""
import hashlib
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from app.core.config import get_settings
from app.storage.chunk_store import ChunkStore
from shared.constants import INTERNAL_API_PREFIX, INTERNAL_TOKEN_HEADER
from shared.exceptions import ChunkNotFoundError
from shared.models import ChunkReport, ChunkVerifyResult


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias=INTERNAL_TOKEN_HEADER),
) -> None:
    """Validate internal authentication token passed in request headers."""
    if x_internal_token != get_settings().internal_api_token:
        raise HTTPException(status_code=401, detail="Invalid internal token")


def get_store() -> ChunkStore:
    """FastAPI dependency providing ChunkStore instance bound to storage directory."""
    return ChunkStore(get_settings().storage_dir)


router = APIRouter(
    prefix=f"{INTERNAL_API_PREFIX}/chunks",
    tags=["chunks"],
    dependencies=[Depends(require_internal_token)],
)


@router.put("/{chunk_id}", status_code=204)
async def put_chunk(chunk_id: str, request: Request, store: ChunkStore = Depends(get_store)):
    """Receive and atomically persist chunk binary data to disk."""
    data = await request.body()
    store.write(chunk_id, data)
    return Response(status_code=204)


@router.get("/{chunk_id}")
def get_chunk(chunk_id: str, store: ChunkStore = Depends(get_store)):
    """Retrieve and stream raw chunk bytes from disk."""
    try:
        data = store.read(chunk_id)
        return Response(content=data, media_type="application/octet-stream")
    except ChunkNotFoundError:
        raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found")


@router.delete("/{chunk_id}", status_code=204)
def delete_chunk(chunk_id: str, store: ChunkStore = Depends(get_store)):
    """Remove a chunk file from local disk."""
    store.delete(chunk_id)
    return Response(status_code=204)


@router.api_route("/{chunk_id}/verify", methods=["GET", "POST"], response_model=ChunkVerifyResult)
def verify_chunk(chunk_id: str, store: ChunkStore = Depends(get_store)):
    """Compute and return current SHA-256 checksum and size of a stored chunk."""
    # Check if file exists on disk
    if not store.exists(chunk_id):
        return ChunkVerifyResult(chunk_id=chunk_id, exists=False)
    # Read chunk and compute live checksum
    data = store.read(chunk_id)
    return ChunkVerifyResult(
        chunk_id=chunk_id,
        exists=True,
        checksum=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )


@router.get("", response_model=list[ChunkReport])
def list_chunks(store: ChunkStore = Depends(get_store)):
    """List all stored chunks on this worker with their sizes and checksums."""
    return store.list_chunks()
