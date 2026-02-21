"""SQLAlchemy ORM models."""

from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Time, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base


class Customer(Base):
    """Represents a garage customer."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    vehicles: Mapped[list["Vehicle"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )


class Vehicle(Base):
    """Represents a vehicle owned by a customer."""

    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vehicle_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    customer: Mapped["Customer"] = relationship(back_populates="vehicles")
    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="vehicle",
        cascade="all, delete-orphan",
    )


class Booking(Base):
    """Represents a service booking for a specific vehicle."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), nullable=False, index=True)
    service_type: Mapped[str] = mapped_column(String(100), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    service_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    reminder_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    reminder_message_sid: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        default=None,
    )

    delivery_status: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        default=None,
)

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    vehicle: Mapped["Vehicle"] = relationship(back_populates="bookings")
