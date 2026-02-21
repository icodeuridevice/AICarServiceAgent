"""Database engine/session setup for SQLAlchemy."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# SQLite database file in the project root.
DATABASE_URL = "sqlite:///./garage.db"

# Engine is shared across requests; check_same_thread is required for SQLite with FastAPI.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

# Session factory used by request-scoped dependencies.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)

# Declarative base class for ORM models.
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Provide a DB session per request and ensure it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
