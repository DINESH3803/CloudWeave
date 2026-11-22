"""Client-facing object endpoints. Route handlers delegate to services."""
import json
import logging
import os
import unicodedata
import urllib.parse
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.metadata import MetadataPatchRequest, ObjectMetadataOut
from app.schemas.objects import ObjectListOut, ObjectOut
from app.services.metadata_service import MetadataService
from app.services.object_service import ObjectService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/objects", tags=["objects"])


def _format_content_disposition(name: str) -> str:
    """Format RFC 6266 / RFC 5987 Content-Disposition header with safe ASCII fallback."""
    base, ext = os.path.splitext(name)
    ascii_base = "".join(
        c if c.isalnum() or c in "-_ " else "_"
        for c in unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    ).strip()
    ascii_ext = "".join(c if c.isalnum() else "" for c in ext.lstrip(".")).strip()
    fallback = f"{ascii_base or 'download'}.{ascii_ext}" if ascii_ext else (ascii_base or "download")
    quoted_utf8 = urllib.parse.quote(name, encoding="utf-8")
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quoted_utf8}'


@router.post("", response_model=ObjectOut, status_code=201)
def upload_object(
    file: UploadFile = File(...),
    metadata: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    custom_metadata = {}
    if metadata:
        try:
            parsed = json.loads(metadata)
            if not isinstance(parsed, dict):
                raise HTTPException(status_code=400, detail="metadata must be a JSON object")
            custom_metadata = parsed
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON in metadata: {e}")

    return ObjectService(db).upload(
        name=file.filename or "unnamed",
        content_type=file.content_type,
        stream=file.file,
        custom_metadata=custom_metadata,
    )


@router.get("", response_model=ObjectListOut)
def list_objects(
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int = Query(default=100, ge=1, le=1000, description="Pagination limit"),
    db: Session = Depends(get_db),
):
    items, total = ObjectService(db).list(offset, limit)
    return ObjectListOut(items=items, total=total)


@router.get("/{object_id}")
def download_object(object_id: str, db: Session = Depends(get_db)):
    service = ObjectService(db)
    obj, data_iter = service.download(object_id)
    return StreamingResponse(
        data_iter,
        media_type=obj.content_type or "application/octet-stream",
        headers={"Content-Disposition": _format_content_disposition(obj.name)},
    )


@router.get("/{object_id}/metadata", response_model=ObjectMetadataOut)
def get_object_metadata(object_id: str, db: Session = Depends(get_db)):
    return MetadataService(db).get_object_metadata(object_id)


@router.patch("/{object_id}/metadata", response_model=ObjectMetadataOut)
def patch_object_metadata(
    object_id: str,
    body: MetadataPatchRequest,
    db: Session = Depends(get_db),
):
    return MetadataService(db).patch_custom_metadata(object_id, body.custom_metadata)


@router.delete("/{object_id}", status_code=204)
def delete_object(object_id: str, db: Session = Depends(get_db)):
    ObjectService(db).delete(object_id)
    return Response(status_code=204)
