"""
Database Engine and Session Management.

Sets up the SQLAlchemy connection pool, session factory, request-scoped DB dependency,
and database table initialization.
"""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base

# Engine with connection health checking enabled (pool_pre_ping=True)
engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """
    Provide a request-scoped database session for FastAPI dependencies.
    
    Opens a new session per request and ensures it is safely closed upon completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database schema by creating all registered tables if they do not exist.
    
    Imports models to register them on Base.metadata before creating tables.
    """
    from app.db import models  # noqa: F401 (registers models on Base.metadata)

    Base.metadata.create_all(bind=engine)
