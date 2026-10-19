"""Chunk storage endpoints, called only by the controller."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from app.core.config import get_settings
from app.storage.chunk_store import ChunkStore
from shared.constants import INTERNAL_API_PREFIX, INTERNAL_TOKEN_HEADER
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
    store.write(chunk_id, await request.body())


@router.get("/{chunk_id}")
def get_chunk(chunk_id: str, store: ChunkStore = Depends(get_store)):
    return Response(content=store.read(chunk_id), media_type="application/octet-stream")


@router.delete("/{chunk_id}", status_code=204)
def delete_chunk(chunk_id: str, store: ChunkStore = Depends(get_store)):
    store.delete(chunk_id)


@router.post("/{chunk_id}/verify", response_model=ChunkVerifyResult)
def verify_chunk(chunk_id: str, store: ChunkStore = Depends(get_store)):
    """Re-hash the stored chunk and report its checksum and size."""
    raise NotImplementedError


@router.get("", response_model=list[ChunkReport])
def list_chunks(store: ChunkStore = Depends(get_store)):
    return store.list_chunks()
