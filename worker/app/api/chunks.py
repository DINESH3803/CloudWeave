"""Chunk storage endpoints, called only by the controller."""
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
    if x_internal_token != get_settings().internal_api_token:
        raise HTTPException(status_code=401, detail="Invalid internal token")


def get_store() -> ChunkStore:
    return ChunkStore(get_settings().storage_dir)


router = APIRouter(
    prefix=f"{INTERNAL_API_PREFIX}/chunks",
    tags=["chunks"],
    dependencies=[Depends(require_internal_token)],
)


@router.put("/{chunk_id}", status_code=204)
async def put_chunk(chunk_id: str, request: Request, store: ChunkStore = Depends(get_store)):
    data = await request.body()
    store.write(chunk_id, data)
    return Response(status_code=204)


@router.get("/{chunk_id}")
def get_chunk(chunk_id: str, store: ChunkStore = Depends(get_store)):
    try:
        data = store.read(chunk_id)
        return Response(content=data, media_type="application/octet-stream")
    except ChunkNotFoundError:
        raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found")


@router.delete("/{chunk_id}", status_code=204)
def delete_chunk(chunk_id: str, store: ChunkStore = Depends(get_store)):
    store.delete(chunk_id)
    return Response(status_code=204)


@router.api_route("/{chunk_id}/verify", methods=["GET", "POST"], response_model=ChunkVerifyResult)
def verify_chunk(chunk_id: str, store: ChunkStore = Depends(get_store)):
    """Re-hash the stored chunk and report its checksum and size."""
    if not store.exists(chunk_id):
        return ChunkVerifyResult(chunk_id=chunk_id, exists=False)
    data = store.read(chunk_id)
    return ChunkVerifyResult(
        chunk_id=chunk_id,
        exists=True,
        checksum=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )


@router.get("", response_model=list[ChunkReport])
def list_chunks(store: ChunkStore = Depends(get_store)):
    return store.list_chunks()
