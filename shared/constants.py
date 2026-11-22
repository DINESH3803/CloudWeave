"""
Shared System Constants.
Defines parameters shared across controller, worker, client, and test components:
- Fixed 1 MB chunk sizing and replication factor of 2.
- Internal authentication header and API path prefix.
- Worker, object, and replica lifecycle states.
"""

# Storage chunking and replication configuration
CHUNK_SIZE_BYTES: int = 1024 * 1024  # 1 MB fixed chunk size
REPLICATION_FACTOR: int = 2          # Maintain 2 copies per chunk
CHECKSUM_ALGORITHM: str = "sha256"   # SHA-256 integrity digest

# Internal communication authentication
INTERNAL_TOKEN_HEADER: str = "X-Internal-Token"
INTERNAL_API_PREFIX: str = "/internal"

# Worker node status states
WORKER_STATUS_ACTIVE: str = "active"
WORKER_STATUS_UNHEALTHY: str = "unhealthy"
WORKER_STATUS_OFFLINE: str = "offline"

# Stored object lifecycle states
OBJECT_STATUS_UPLOADING: str = "uploading"
OBJECT_STATUS_AVAILABLE: str = "available"
OBJECT_STATUS_DEGRADED: str = "degraded"
OBJECT_STATUS_DELETING: str = "deleting"

# Chunk replica health states
REPLICA_STATUS_PENDING: str = "pending"
REPLICA_STATUS_STORED: str = "stored"
REPLICA_STATUS_CORRUPT: str = "corrupt"
REPLICA_STATUS_MISSING: str = "missing"
