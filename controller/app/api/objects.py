"""
Client-Facing Object Endpoints.

Handles object upload, download, listing, metadata updates, and deletion.
These endpoints interact directly with clients and delegate storage logic
to ObjectService and MetadataService.
"""
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
    """
    Upload a new object to the distributed storage cluster.
    
    Accepts multipart file upload, parses optional JSON custom metadata,
    splits the file into chunks, replicates across workers, and records metadata in DB.
    """
    custom_metadata = {}
    if metadata:
        try:
            # Parse user-supplied JSON metadata string into a dictionary
            parsed = json.loads(metadata)
            if not isinstance(parsed, dict):
                raise HTTPException(status_code=400, detail="metadata must be a JSON object")
            custom_metadata = parsed
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON in metadata: {e}")

    # Delegate chunking, replica placement, and storage to ObjectService
    return ObjectService(db).upload(
        name=file.filename or "unnamed",
        content_type=file.content_type,
        stream=file.file,
        custom_metadata=custom_metadata,
    )


@router.get("", response_model=ObjectListOut)
def list_objects(offset: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    List stored objects with pagination.
    
    Returns a paginated list of objects and the total count in the system.
    """
    # Fetch paginated items and total count from database
    items, total = ObjectService(db).list(offset, limit)
    return ObjectListOut(items=items, total=total)


@router.get("/{object_id}")
def download_object(object_id: str, db: Session = Depends(get_db)):
    """
    Download and reassemble an object by its ID.
    
    Streams the reassembled chunks back to the client transparently without
    the client needing to know which workers store the chunks.
    """
    service = ObjectService(db)
    # Check if object exists and retrieve its content type and file name
    obj = service.get(object_id)
    
    # Stream chunks in sequence from healthy workers with automatic failover
    return StreamingResponse(
        service.download(object_id),
        media_type=obj.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{obj.name}"'},
    )


@router.get("/{object_id}/metadata", response_model=ObjectMetadataOut)
def get_object_metadata(object_id: str, db: Session = Depends(get_db)):
    """
    Retrieve full metadata for an object.
    
    Returns object details including chunk list, replica locations, and custom metadata.
    """
    # Fetch complete object metadata including chunks and replicas
    return MetadataService(db).get_object_metadata(object_id)


@router.patch("/{object_id}/metadata", response_model=ObjectMetadataOut)
def patch_object_metadata(
    object_id: str,
    body: MetadataPatchRequest,
    db: Session = Depends(get_db),
):
    """
    Modify an object's custom metadata without re-uploading file chunks.
    
    Merges updated keys into existing metadata (or removes keys set to null).
    """
    # In-place JSON metadata update on the database record
    return MetadataService(db).patch_custom_metadata(object_id, body.custom_metadata)


@router.delete("/{object_id}", status_code=204)
def delete_object(object_id: str, db: Session = Depends(get_db)):
    """
    Delete an object and clean up all its chunks across all worker nodes.
    
    Deletes chunk files from workers and marks records as deleted in the database.
    """
    # Instruct workers to delete chunk files and remove database entries
    ObjectService(db).delete(object_id)
    return Response(status_code=204)
