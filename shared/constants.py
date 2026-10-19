"""Constants shared by the controller, workers and client."""

# --- Storage parameters -----------------------------------------------------
CHUNK_SIZE_BYTES: int = 1024 * 1024  # 1 MB
REPLICATION_FACTOR: int = 2
CHECKSUM_ALGORITHM: str = "sha256"

# --- Internal controller <-> worker HTTP contract ---------------------------
INTERNAL_TOKEN_HEADER: str = "X-Internal-Token"
INTERNAL_API_PREFIX: str = "/internal"

# --- Worker lifecycle states ------------------------------------------------
WORKER_STATUS_ACTIVE: str = "active"
WORKER_STATUS_UNHEALTHY: str = "unhealthy"
WORKER_STATUS_OFFLINE: str = "offline"

# --- Object lifecycle states ------------------------------------------------
OBJECT_STATUS_UPLOADING: str = "uploading"
OBJECT_STATUS_AVAILABLE: str = "available"
OBJECT_STATUS_DEGRADED: str = "degraded"
OBJECT_STATUS_DELETING: str = "deleting"

# --- Chunk replica states ---------------------------------------------------
REPLICA_STATUS_PENDING: str = "pending"
REPLICA_STATUS_STORED: str = "stored"
REPLICA_STATUS_CORRUPT: str = "corrupt"
REPLICA_STATUS_MISSING: str = "missing"
