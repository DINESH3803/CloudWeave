"""
ORM Models for Controller Metadata Database.

Defines the relational schema:
- Worker: Registered storage nodes, heartbeat times, status, disk usage.
- StoredObject: High-level objects uploaded by clients, hashes, custom metadata.
- Chunk: Fixed-size 1 MB subdivisions of an object.
- ChunkReplica: Join table mapping chunks to worker nodes (replication factor 2).
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from shared.constants import (
    OBJECT_STATUS_UPLOADING,
    REPLICA_STATUS_STORED,
    WORKER_STATUS_ACTIVE,
)


class Worker(Base):
    """
    Worker node database entity.
    
    Tracks a storage node's network address, health status, capacity, and last heartbeat.
    """
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    base_url: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default=WORKER_STATUS_ACTIVE)
    capacity_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    used_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StoredObject(Base):
    """
    Stored object database entity.
    
    Represents a client-uploaded file with name, overall size, composite checksum,
    custom JSON metadata, and timestamps.
    """
    __tablename__ = "objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default=OBJECT_STATUS_UPLOADING)
    custom_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 1-to-many relationship: An object is composed of ordered chunks
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="object", cascade="all, delete-orphan", order_by="Chunk.chunk_index"
    )


class Chunk(Base):
    """
    Chunk database entity.
    
    Represents a discrete part of an object (up to 1 MB) with its sequence index and SHA-256 checksum.
    """
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("object_id", "chunk_index"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_id: Mapped[str] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="stored")

    object: Mapped[StoredObject] = relationship(back_populates="chunks")
    # 1-to-many relationship: A chunk has multiple physical replicas across workers
    replicas: Mapped[list["ChunkReplica"]] = relationship(
        back_populates="chunk", cascade="all, delete-orphan"
    )


class ChunkReplica(Base):
    """
    Chunk replica database entity.
    
    Associates a chunk with the specific worker node storing that replica copy.
    """
    __tablename__ = "chunk_replicas"

    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True
    )
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default=REPLICA_STATUS_STORED)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chunk: Mapped[Chunk] = relationship(back_populates="replicas")
    worker: Mapped[Worker] = relationship()
