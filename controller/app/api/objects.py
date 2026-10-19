"""Client-facing object endpoints. Route handlers only delegate to services."""
from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.objects import ObjectListOut, ObjectOut
from app.services.object_service import ObjectService

router = APIRouter(prefix="/objects", tags=["objects"])


@router.post("", response_model=ObjectOut, status_code=201)
def upload_object(file: UploadFile, db: Session = Depends(get_db)):
    return ObjectService(db).upload(file.filename or "unnamed", file.content_type, file.file)


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


@router.delete("/{object_id}", status_code=204)
def delete_object(object_id: str, db: Session = Depends(get_db)):
    ObjectService(db).delete(object_id)
    return Response(status_code=204)
