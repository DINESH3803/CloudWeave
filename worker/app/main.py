"""
CloudWeave Storage Worker Entry Point.
Manages worker startup lifecycle:
- Configures standard stdout logging.
- Creates local chunk storage folder on disk.
- Spawns background HeartbeatReporter to register and heartbeat with the controller.
- Serves internal chunk API routes (/internal/chunks) and health checks.
"""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import chunks, worker
from app.core.config import get_settings
from app.heartbeat.reporter import HeartbeatReporter
from app.storage.chunk_store import ChunkStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Manage worker startup registration, heartbeat reporter background loop, and shutdown."""
    settings = get_settings()
    # Configure stdout logging format
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    # Ensure persistent storage directory exists
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    store = ChunkStore(settings.storage_dir)
    # Start heartbeat reporter background task
    reporter = HeartbeatReporter(store, settings)
    reporter.start()
    logger.info("Worker %s started, storage=%s", settings.worker_id, settings.storage_dir)
    try:
        yield
    finally:
        # Cleanly terminate reporter on process shutdown
        reporter.stop()
        logger.info("Worker %s stopped", settings.worker_id)


def create_app() -> FastAPI:
    """Create and configure FastAPI application for the storage worker."""
    app = FastAPI(title="CloudWeave Worker", lifespan=lifespan)
    # Mount worker identity/health routes and internal chunk storage routes
    app.include_router(worker.router)
    app.include_router(chunks.router)

    @app.exception_handler(NotImplementedError)
    async def _not_implemented(_: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(status_code=501, content={"detail": str(exc) or "Not implemented yet"})

    return app


# Application instance for ASGI server (uvicorn)
app = create_app()
