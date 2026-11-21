"""Background monitor: marks workers unhealthy when heartbeats stop, and keeps
replication reconciliation running.

Every tick (``health_check_interval_seconds``):
1. workers whose last heartbeat is older than ``heartbeat_timeout_seconds`` are marked
   unhealthy (own session, rolled back on error);
2. a replication reconciliation pass runs if one is due
   (``replication_reconcile_interval_seconds``), or immediately when a worker has just
   been marked unhealthy.

Ticks run in a worker thread (``asyncio.to_thread``), so database and HTTP work does
not block the controller's event loop. An exception in one tick is logged and never
stops the loop.
"""
import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Worker
from app.db.session import SessionLocal
from app.scheduler.replication import ReplicationManager
from shared.constants import WORKER_STATUS_ACTIVE, WORKER_STATUS_UNHEALTHY

logger = logging.getLogger(__name__)


class HealthMonitor:
    def __init__(
        self,
        session_factory: Callable[[], Session] | None = None,
        replication_manager: ReplicationManager | None = None,
    ) -> None:
        self.settings = get_settings()
        self.session_factory = session_factory or SessionLocal
        self.replication = replication_manager or ReplicationManager(session_factory=self.session_factory)
        self._last_reconcile: float | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    def mark_unhealthy_workers(self) -> int:
        """Mark workers whose last heartbeat exceeds the timeout. Returns how many were marked."""
        db = self.session_factory()
        try:
            now = datetime.now(timezone.utc)
            marked = 0
            for w in db.query(Worker).all():
                if w.status != WORKER_STATUS_ACTIVE or w.last_heartbeat is None:
                    continue
                age = (now - w.last_heartbeat).total_seconds()
                if age > self.settings.heartbeat_timeout_seconds:
                    logger.warning(
                        "Worker %s timed out (last heartbeat %0.1fs ago > %ds); marking UNHEALTHY",
                        w.id,
                        age,
                        self.settings.heartbeat_timeout_seconds,
                    )
                    w.status = WORKER_STATUS_UNHEALTHY
                    marked += 1
            if marked:
                db.commit()
            return marked
        except Exception as e:
            db.rollback()
            logger.warning("Health check failed (will retry next tick): %s: %s", type(e).__name__, str(e).splitlines()[0][:200] if str(e) else "")
            return 0
        finally:
            db.close()

    def check_once(self) -> None:
        """One monitor tick: update worker health, then reconcile replication if due."""
        marked = self.mark_unhealthy_workers()
        now = time.monotonic()
        due = (
            self._last_reconcile is None
            or now - self._last_reconcile >= self.settings.replication_reconcile_interval_seconds
        )
        if marked or due:
            self._last_reconcile = now
            try:
                self.replication.reconcile_once()
            except Exception:
                logger.exception("Replication reconciliation pass failed; will retry next cycle")

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.settings.health_check_interval_seconds)
            if not self._running:
                break
            try:
                await asyncio.to_thread(self.check_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Health monitor tick failed; continuing")

    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Health monitor started: health check every %ss, replication reconciliation every %ss "
            "(retry backoff %ss..%ss, replication factor %d)",
            self.settings.health_check_interval_seconds,
            self.settings.replication_reconcile_interval_seconds,
            self.settings.replication_retry_base_seconds,
            self.settings.replication_retry_max_seconds,
            self.settings.replication_factor,
        )

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
