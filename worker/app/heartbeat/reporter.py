"""Registers with the controller and sends periodic heartbeats."""
import logging

from app.core.config import WorkerSettings, get_settings
from app.storage.chunk_store import ChunkStore
from shared.models import WorkerHeartbeat, WorkerRegistration

logger = logging.getLogger(__name__)


class HeartbeatReporter:
    def __init__(self, store: ChunkStore, settings: WorkerSettings | None = None) -> None:
        self.store = store
        self.settings = settings or get_settings()

    def build_registration(self) -> WorkerRegistration:
        """Describe this worker and its stored chunks for the controller."""
        raise NotImplementedError

    def build_heartbeat(self) -> WorkerHeartbeat:
        raise NotImplementedError

    def register(self) -> None:
        """POST the registration to the controller (retry until it succeeds)."""
        raise NotImplementedError

    def start(self) -> None:
        """Register, then send heartbeats every heartbeat_interval_seconds in the background."""
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError
