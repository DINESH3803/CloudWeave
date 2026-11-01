"""Client-facing object endpoints. Route handlers delegate to services."""
import json
import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.metadata import MetadataPatchRequest, ObjectMetadataOut
from app.schemas.objects import ObjectListOut, ObjectOut
from app.services.metadata_service import MetadataService
from app.services.object_service import ObjectService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/objects", tags=["objects"])


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
def list_objects(offset: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    items, total = ObjectService(db).list(offset, limit)
    return ObjectListOut(items=items, total=total)


@router.get("/{object_id}")
def download_object(object_id: str, db: Session = Depends(get_db)):
    service = ObjectService(db)
    obj = service.get(object_id)
    return StreamingResponse(
        service.download(object_id),
        media_type=obj.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{obj.name}"'},
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
