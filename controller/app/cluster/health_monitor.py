"""Background monitor that marks workers unhealthy when heartbeats stop."""
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
    def __init__(self) -> None:
        self.settings = get_settings()
        self._running = False
        self._task: asyncio.Task | None = None

    def check_once(self) -> None:
        """Mark workers whose last heartbeat exceeds heartbeat_timeout_seconds, trigger re-replication."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            workers = db.query(Worker).all()
            changed = False
            for w in workers:
                if w.status == WORKER_STATUS_ACTIVE:
                    if w.last_heartbeat is None:
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
                        changed = True

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
        while self._running:
            await asyncio.sleep(self.settings.health_check_interval_seconds)
            if not self._running:
                break
            self.check_once()

    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
