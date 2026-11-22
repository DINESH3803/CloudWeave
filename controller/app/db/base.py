"""
SQLAlchemy Declarative Base.

Defines the base class inherited by all ORM model classes in the controller.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative mapping models."""
    pass
