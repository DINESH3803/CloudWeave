"""
Heartbeat and Registration Reporter for Worker Nodes.
Registers worker on boot with inventory of local chunks,
and sends periodic heartbeats with current disk usage to the controller.
"""
import asyncio
from datetime import datetime, timezone
import logging

import httpx

from app.core.config import WorkerSettings, get_settings
from app.storage.chunk_store import ChunkStore
from shared.constants import INTERNAL_API_PREFIX, INTERNAL_TOKEN_HEADER
from shared.models import WorkerHeartbeat, WorkerRegistration

logger = logging.getLogger(__name__)


class HeartbeatReporter:
    """Manages background registration and periodic heartbeat transmissions to controller."""

    def __init__(self, store: ChunkStore, settings: WorkerSettings | None = None) -> None:
        self.store = store
        self.settings = settings or get_settings()
        self._task: asyncio.Task | None = None
        self._running = False

    def build_registration(self) -> WorkerRegistration:
        """Construct registration payload with worker metadata and local chunk inventory."""
        chunks = self.store.list_chunks()
        return WorkerRegistration(
            worker_id=self.settings.worker_id,
            base_url=self.settings.advertise_url,
            capacity_bytes=self.settings.capacity_bytes,
            used_bytes=self.store.used_bytes(),
            chunks=chunks,
        )

    def build_heartbeat(self) -> WorkerHeartbeat:
        """Construct heartbeat payload reporting current disk usage and chunk count."""
        chunks = self.store.list_chunks()
        return WorkerHeartbeat(
            worker_id=self.settings.worker_id,
            used_bytes=self.store.used_bytes(),
            chunk_count=len(chunks),
            sent_at=datetime.now(timezone.utc),
        )

    async def register(self) -> bool:
        """Send registration POST request to the controller; returns True on success."""
        reg = self.build_registration()
        url = f"{self.settings.controller_url.rstrip('/')}{INTERNAL_API_PREFIX}/workers/register"
        headers = {INTERNAL_TOKEN_HEADER: self.settings.internal_api_token}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=reg.model_dump(mode="json"), headers=headers)
                if resp.status_code in (200, 201):
                    logger.info("Worker %s successfully registered with controller", self.settings.worker_id)
                    return True
                logger.warning("Controller returned %s on register: %s", resp.status_code, resp.text)
        except Exception as e:
            logger.debug("Failed to connect to controller during registration: %s", e)
        return False

    async def send_heartbeat(self) -> bool:
        """Send periodic heartbeat ping to controller; returns True on success."""
        hb = self.build_heartbeat()
        url = f"{self.settings.controller_url.rstrip('/')}{INTERNAL_API_PREFIX}/workers/heartbeat"
        headers = {INTERNAL_TOKEN_HEADER: self.settings.internal_api_token}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=hb.model_dump(mode="json"), headers=headers)
                if resp.status_code in (200, 204):
                    return True
                logger.warning("Controller returned %s on heartbeat", resp.status_code)
        except Exception as e:
            logger.warning("Failed to send heartbeat to controller: %s", e)
        return False

    async def _loop(self) -> None:
        """Background asynchronous loop handling initial registration and recurring heartbeats."""
        # 1. Keep retrying initial registration until controller is reachable
        registered = False
        while self._running and not registered:
            registered = await self.register()
            if not registered:
                await asyncio.sleep(2.0)

        # 2. Transmit heartbeats at configured intervals
        while self._running:
            await asyncio.sleep(self.settings.heartbeat_interval_seconds)
            if not self._running:
                break
            success = await self.send_heartbeat()
            # If heartbeat failed, attempt re-registration on next tick
            if not success:
                logger.info("Heartbeat failed, will try re-registering...")
                await self.register()

    def start(self) -> None:
        """Start the background reporter task."""
        self._running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        """Stop and cancel the background reporter task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
