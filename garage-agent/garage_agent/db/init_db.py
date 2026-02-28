"""Database initialization utilities."""

from sqlalchemy import inspect, text

from garage_agent.db import models  # noqa: F401 - ensure model metadata is registered
from garage_agent.db.session import Base, engine


def _ensure_column(table_name: str, column_name: str, column_ddl: str) -> None:
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in existing_columns:
        return

    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_ddl}"))


def init_db() -> None:
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(bind=engine)
    _ensure_column(
        table_name="customers",
        column_name="health_score",
        column_ddl="health_score INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(
        table_name="vehicles",
        column_name="next_service_due_date",
        column_ddl="next_service_due_date DATE",
    )
