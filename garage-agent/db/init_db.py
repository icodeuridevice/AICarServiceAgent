"""Database initialization utilities."""

from db import models  # noqa: F401 - ensure model metadata is registered
from db.session import Base, engine


def init_db() -> None:
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(bind=engine)
