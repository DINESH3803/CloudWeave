"""Metadata inspection endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.metadata import ClusterStatusOut, ObjectMetadataOut
from app.services.metadata_service import MetadataService

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/objects/{object_id}", response_model=ObjectMetadataOut)
def get_object_metadata(object_id: str, db: Session = Depends(get_db)):
    return MetadataService(db).get_object_metadata(object_id)


@router.get("/cluster", response_model=ClusterStatusOut)
def get_cluster_status(db: Session = Depends(get_db)):
    settings = get_settings()
    return ClusterStatusOut(
        workers=MetadataService(db).get_cluster_workers(),
        replication_factor=settings.replication_factor,
        chunk_size_bytes=settings.chunk_size_bytes,
    )
