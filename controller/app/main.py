"""CloudWeave controller entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import internal_workers, metadata, objects
from app.core.config import get_settings
from app.core.exceptions import install_exception_handlers
from app.core.logging import setup_logging
from app.db.session import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    init_db()
    # TODO(next step): start HealthMonitor and periodic integrity scans here.
    logger.info("Controller started")
    yield
    logger.info("Controller stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    install_exception_handlers(app)
    app.include_router(objects.router)
    app.include_router(metadata.router)
    app.include_router(internal_workers.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
