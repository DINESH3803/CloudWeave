"""Background monitor that marks workers unhealthy when heartbeats stop."""
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class HealthMonitor:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._running = False

    def start(self) -> None:
        """Start the periodic check loop (background thread/task)."""
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def check_once(self) -> None:
        """Mark workers whose last heartbeat exceeds heartbeat_timeout_seconds, trigger re-replication."""
        raise NotImplementedError
