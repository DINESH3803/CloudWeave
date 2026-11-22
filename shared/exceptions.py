"""
Domain Exceptions for CloudWeave.
Shared exception hierarchy mapped to HTTP status codes by the controller
and raised by workers, services, and client components.
"""


class CloudWeaveError(Exception):
    """Base exception class for all CloudWeave errors."""


class ObjectNotFoundError(CloudWeaveError):
    """Raised when an object ID does not exist in the metadata store (HTTP 404)."""


class ChunkNotFoundError(CloudWeaveError):
    """Raised when a chunk ID does not exist on disk or in metadata (HTTP 404)."""


class WorkerNotFoundError(CloudWeaveError):
    """Raised when an operation references an unregistered worker (HTTP 404)."""


class WorkerUnavailableError(CloudWeaveError):
    """Raised when a worker cannot be contacted or is offline (HTTP 503)."""


class NoHealthyWorkersError(CloudWeaveError):
    """Raised when there are not enough active workers to satisfy replication (HTTP 503)."""


class ChecksumMismatchError(CloudWeaveError):
    """Raised when chunk data corruption or bitrot is detected (HTTP 500)."""


class ConflictError(CloudWeaveError):
    """Raised on concurrent write conflict or invalid state transition (HTTP 409)."""


class InvalidRequestError(CloudWeaveError):
    """Raised on malformed or invalid request parameters (HTTP 400)."""
