"""Registers with the controller and sends periodic heartbeats."""
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
    def __init__(self, store: ChunkStore, settings: WorkerSettings | None = None) -> None:
        self.store = store
        self.settings = settings or get_settings()
        self._task: asyncio.Task | None = None
        self._running = False

    def build_registration(self) -> WorkerRegistration:
        """Describe this worker and its stored chunks for the controller."""
        chunks = self.store.list_chunks()
        return WorkerRegistration(
            worker_id=self.settings.worker_id,
            base_url=self.settings.advertise_url,
            capacity_bytes=self.settings.capacity_bytes,
            used_bytes=self.store.used_bytes(),
            chunks=chunks,
        )

    def build_heartbeat(self) -> WorkerHeartbeat:
        chunks = self.store.list_chunks()
        return WorkerHeartbeat(
            worker_id=self.settings.worker_id,
            used_bytes=self.store.used_bytes(),
            chunk_count=len(chunks),
            sent_at=datetime.now(timezone.utc),
        )

    async def register(self) -> bool:
        """POST registration to the controller, returns True on success."""
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
        # Keep trying to register until controller is available
        registered = False
        while self._running and not registered:
            registered = await self.register()
            if not registered:
                await asyncio.sleep(2.0)

        while self._running:
            await asyncio.sleep(self.settings.heartbeat_interval_seconds)
            if not self._running:
                break
            success = await self.send_heartbeat()
            if not success:
                # If heartbeat fails, attempt re-registration on next interval
                logger.info("Heartbeat failed, will try re-registering...")
                await self.register()

    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
