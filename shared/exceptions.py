"""Domain exceptions shared by all CloudWeave components."""


class CloudWeaveError(Exception):
    """Base class for all CloudWeave errors."""


class ObjectNotFoundError(CloudWeaveError):
    """The requested object does not exist."""

    def __init__(self, object_id: str | None = None) -> None:
        self.object_id = object_id
        if object_id:
            msg = object_id if object_id.startswith("Object ") else f"Object {object_id} not found"
        else:
            msg = "Object not found"
        super().__init__(msg)


class ChunkNotFoundError(CloudWeaveError):
    """The requested chunk does not exist on the worker / in metadata."""


class WorkerNotFoundError(CloudWeaveError):
    """The referenced worker is not registered."""


class WorkerUnavailableError(CloudWeaveError):
    """A worker could not be reached."""


class NoHealthyWorkersError(CloudWeaveError):
    """Not enough healthy workers to satisfy the replication factor."""


class ChecksumMismatchError(CloudWeaveError):
    """Chunk or object data does not match its recorded checksum."""


class ConflictError(CloudWeaveError):
    """The request conflicts with current state."""


class InvalidRequestError(CloudWeaveError):
    """The request is invalid or malformed."""


class ObjectIntegrityError(CloudWeaveError):
    """Reconstructed object fails size or checksum validation."""
