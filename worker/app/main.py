"""CloudWeave storage worker entry point."""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import chunks, worker
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    # TODO(next step): create HeartbeatReporter(ChunkStore(...)) and start() it here.
    logger.info("Worker %s started, storage=%s", settings.worker_id, settings.storage_dir)
    yield
    logger.info("Worker %s stopped", settings.worker_id)


def create_app() -> FastAPI:
    app = FastAPI(title="CloudWeave Worker", lifespan=lifespan)
    app.include_router(worker.router)
    app.include_router(chunks.router)

    @app.exception_handler(NotImplementedError)
    async def _not_implemented(_: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(status_code=501, content={"detail": str(exc) or "Not implemented yet"})

    return app


app = create_app()
