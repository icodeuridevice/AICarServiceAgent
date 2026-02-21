"""Database initialization utilities."""

from garage_agent.db import models  # noqa: F401 - ensure model metadata is registered
from garage_agent.db.session import Base, engine


def init_db() -> None:
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(bind=engine)
