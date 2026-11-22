"""
CloudWeave Controller Entry Point.

Initializes the FastAPI application, manages application lifespan (starting DB
and background health monitor), configures logging, registers exception handlers,
and mounts API routers.
"""
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
    """
    Manage startup and shutdown events for the FastAPI application.
    
    On startup:
      - Sets up logging formatting.
      - Creates database tables if they do not exist.
      - Starts the background health monitor thread for worker health & re-replication.
    On shutdown:
      - Stops the background health monitor thread cleanly.
    """
    # 1. Load application configuration
    settings = get_settings()
    
    # 2. Configure logging level and format
    setup_logging(settings.log_level)
    
    # 3. Initialize database tables
    init_db()
    
    # 4. Start background cluster health monitor
    monitor = HealthMonitor()
    monitor.start()
    logger.info("Controller started (health monitor active)")
    
    try:
        yield
    finally:
        # 5. Cleanly stop background monitoring on server shutdown
        monitor.stop()
        logger.info("Controller stopped")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI controller application.
    
    Sets up custom exception handlers, attaches route handlers, and defines
    the public /health endpoint.
    """
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    
    # Register global domain exception handlers
    install_exception_handlers(app)

    # Register client-facing and internal API routers
    app.include_router(objects.router)
    # Support /objects as prefix alias for convenience
    app.include_router(objects.router, prefix="", include_in_schema=False)
    app.include_router(metadata.router)
    app.include_router(internal_workers.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Check controller service health status."""
        return {"status": "ok"}

    return app


# Application instance for ASGI runners (uvicorn)
app = create_app()
