"""CloudWeave controller entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import internal_workers, metadata, objects
from app.cluster.health_monitor import HealthMonitor
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
    monitor = HealthMonitor()
    monitor.start()
    logger.info("Controller started (health monitor active)")
    try:
        yield
    finally:
        monitor.stop()
        logger.info("Controller stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    install_exception_handlers(app)

    # API Routes
    app.include_router(objects.router)
    # Also support /objects as prefix alias for convenience
    app.include_router(objects.router, prefix="", include_in_schema=False)
    app.include_router(metadata.router)
    app.include_router(internal_workers.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
