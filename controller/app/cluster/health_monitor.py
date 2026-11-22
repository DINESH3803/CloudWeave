"""
Cluster Health Monitor.

Background background monitor loop that:
1. Scans registered workers for missed heartbeats.
2. Marks timed-out workers as UNHEALTHY.
3. Automatically triggers replication repair for any under-replicated chunks.
"""
import asyncio
from datetime import datetime, timezone
import logging

from app.core.config import get_settings
from app.db.models import Worker
from app.db.session import SessionLocal
from app.scheduler.replication import ReplicationManager
from shared.constants import WORKER_STATUS_ACTIVE, WORKER_STATUS_UNHEALTHY

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitors worker health and triggers healing upon failure detection."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._running = False
        self._task: asyncio.Task | None = None

    def check_once(self) -> None:
        """
        Evaluate worker heartbeats and trigger replication restoration if nodes fail.
        
        Marks workers as UNHEALTHY if their last heartbeat timestamp exceeds the timeout threshold.
        """
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            workers = db.query(Worker).all()
            changed = False
            for w in workers:
                if w.status == WORKER_STATUS_ACTIVE:
                    if w.last_heartbeat is None:
                        continue
                    # Calculate how many seconds elapsed since the last heartbeat ping
                    age = (now - w.last_heartbeat).total_seconds()
                    if age > self.settings.heartbeat_timeout_seconds:
                        logger.warning(
                            "Worker %s timed out (last heartbeat %0.1fs ago > %ds); marking UNHEALTHY",
                            w.id,
                            age,
                            self.settings.heartbeat_timeout_seconds,
                        )
                        w.status = WORKER_STATUS_UNHEALTHY
                        changed = True

            # If any worker became unhealthy, commit status and restore under-replicated chunks
            if changed:
                db.commit()
                # Run restoration of under-replicated chunks
                rep_mgr = ReplicationManager(db)
                rep_mgr.restore_replication()
        except Exception as e:
            logger.exception("Error during health monitor check: %s", e)
        finally:
            db.close()

    async def _loop(self) -> None:
        """Async periodic loop executing health checks at configured intervals."""
        while self._running:
            await asyncio.sleep(self.settings.health_check_interval_seconds)
            if not self._running:
                break
            # Run check evaluation
            self.check_once()

    def start(self) -> None:
        """Start the background health monitor task."""
        self._running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        """Stop and cancel the background health monitor task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
