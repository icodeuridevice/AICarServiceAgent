"""Database initialization utilities."""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from garage_agent.db import models  # noqa: F401 - ensure model metadata is registered
from garage_agent.db.session import Base, engine

logger = logging.getLogger(__name__)


def _table_exists(table_name: str) -> bool:
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def _get_columns(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    inspector = inspect(engine)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _ensure_column(table_name: str, column_name: str, column_ddl: str) -> None:
    existing_columns = _get_columns(table_name)
    if column_name in existing_columns:
        return

    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_ddl}"))


def _ensure_index(table_name: str, index_name: str, columns: list[str]) -> None:
    if not _table_exists(table_name):
        return

    columns_sql = ", ".join(columns)
    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {index_name} "
                f"ON {table_name} ({columns_sql})"
            )
        )


def _has_duplicate_rows(
    table_name: str,
    columns: list[str],
    where_clause: str | None = None,
) -> bool:
    if not _table_exists(table_name):
        return False

    columns_sql = ", ".join(columns)
    where_sql = f" WHERE {where_clause}" if where_clause else ""
    duplicate_query = (
        f"SELECT 1 FROM {table_name}"
        f"{where_sql} "
        f"GROUP BY {columns_sql} "
        "HAVING COUNT(*) > 1 "
        "LIMIT 1"
    )
    with engine.connect() as connection:
        return connection.execute(text(duplicate_query)).first() is not None


def _ensure_unique_index_if_clean(
    table_name: str,
    index_name: str,
    columns: list[str],
    where_clause: str | None = None,
) -> None:
    if _has_duplicate_rows(table_name=table_name, columns=columns, where_clause=where_clause):
        logger.warning(
            "Skipping unique index %s on %s due to duplicate existing data.",
            index_name,
            table_name,
        )
        return

    if not _table_exists(table_name):
        return

    columns_sql = ", ".join(columns)
    where_sql = f" WHERE {where_clause}" if where_clause else ""
    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                f"ON {table_name} ({columns_sql}){where_sql}"
            )
        )


def _backfill_null_column(table_name: str, column_name: str, value: int) -> None:
    if column_name not in _get_columns(table_name):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                f"UPDATE {table_name} "
                f"SET {column_name} = :value "
                f"WHERE {column_name} IS NULL"
            ),
            {"value": value},
        )


def _ensure_default_garage() -> int:
    if not _table_exists("garages"):
        raise RuntimeError("garages table is missing after metadata creation.")

    with engine.begin() as connection:
        garage_id = connection.execute(
            text("SELECT id FROM garages ORDER BY id ASC LIMIT 1")
        ).scalar()

        if garage_id is not None:
            return int(garage_id)

        columns = _get_columns("garages")
        if "whatsapp_number" in columns:
            connection.execute(
                text(
                    "INSERT INTO garages (name, phone, whatsapp_number) "
                    "VALUES (:name, :phone, :whatsapp_number)"
                ),
                {
                    "name": "Default Garage",
                    "phone": None,
                    "whatsapp_number": "whatsapp:+10000000000",
                },
            )
        else:
            connection.execute(
                text("INSERT INTO garages (name, phone) VALUES (:name, :phone)"),
                {"name": "Default Garage", "phone": None},
            )

        created_id = connection.execute(
            text("SELECT id FROM garages ORDER BY id ASC LIMIT 1")
        ).scalar_one()

    return int(created_id)


def _backfill_garage_whatsapp_numbers() -> None:
    if "whatsapp_number" not in _get_columns("garages"):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE garages "
                "SET whatsapp_number = 'whatsapp:+10000000000-' || id "
                "WHERE whatsapp_number IS NULL OR TRIM(whatsapp_number) = ''"
            )
        )


def init_db() -> None:
    """Create and migrate schema in a SQLite-safe, additive manner."""
    try:
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
        _ensure_column(
            table_name="vehicles",
            column_name="next_service_date",
            column_ddl="next_service_date DATE",
        )
        _ensure_column(
            table_name="vehicles",
            column_name="next_service_mileage",
            column_ddl="next_service_mileage INTEGER",
        )
        _ensure_column(
            table_name="vehicles",
            column_name="last_reminder_sent_at",
            column_ddl="last_reminder_sent_at DATETIME",
        )
        _ensure_column(
            table_name="garages",
            column_name="whatsapp_number",
            column_ddl="whatsapp_number VARCHAR(32)",
        )

        default_garage_id = _ensure_default_garage()

        for table_name in ("customers", "vehicles", "bookings", "job_cards"):
            _ensure_column(
                table_name=table_name,
                column_name="garage_id",
                column_ddl=f"garage_id INTEGER NOT NULL DEFAULT {default_garage_id}",
            )
            _backfill_null_column(
                table_name=table_name,
                column_name="garage_id",
                value=default_garage_id,
            )
            _ensure_index(
                table_name=table_name,
                index_name=f"ix_{table_name}_garage_id",
                columns=["garage_id"],
            )

        _backfill_garage_whatsapp_numbers()

        _ensure_column(
            table_name="reminders",
            column_name="responded_at",
            column_ddl="responded_at DATETIME",
        )
        _ensure_column(
            table_name="reminders",
            column_name="booking_id",
            column_ddl="booking_id INTEGER REFERENCES bookings(id)",
        )

        _ensure_unique_index_if_clean(
            table_name="garages",
            index_name="uq_garages_whatsapp_number",
            columns=["whatsapp_number"],
            where_clause="whatsapp_number IS NOT NULL AND TRIM(whatsapp_number) <> ''",
        )
        _ensure_unique_index_if_clean(
            table_name="customers",
            index_name="uq_customers_garage_phone",
            columns=["garage_id", "phone"],
            where_clause="phone IS NOT NULL AND TRIM(phone) <> ''",
        )

        # Users table migration (Phase 9.1)
        _ensure_column(
            table_name="users",
            column_name="garage_id",
            column_ddl="garage_id INTEGER NOT NULL DEFAULT 1 REFERENCES garages(id)",
        )
        _ensure_column(
            table_name="users",
            column_name="email",
            column_ddl="email VARCHAR(255) NOT NULL DEFAULT ''",
        )
        _ensure_column(
            table_name="users",
            column_name="hashed_password",
            column_ddl="hashed_password VARCHAR(255) NOT NULL DEFAULT ''",
        )
        _ensure_column(
            table_name="users",
            column_name="role",
            column_ddl="role VARCHAR(32) NOT NULL DEFAULT 'OWNER'",
        )
        _ensure_column(
            table_name="users",
            column_name="is_active",
            column_ddl="is_active BOOLEAN NOT NULL DEFAULT 1",
        )
        _ensure_column(
            table_name="users",
            column_name="created_at",
            column_ddl="created_at DATETIME",
        )
        _ensure_index(
            table_name="users",
            index_name="ix_users_garage_id",
            columns=["garage_id"],
        )
        _ensure_unique_index_if_clean(
            table_name="users",
            index_name="uq_users_email",
            columns=["email"],
            where_clause="email IS NOT NULL AND TRIM(email) <> ''",
        )
    except SQLAlchemyError:
        logger.exception("Database initialization failed.")
        raise
