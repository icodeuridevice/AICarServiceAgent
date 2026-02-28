"""SQLAlchemy ORM models."""

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from garage_agent.db.session import Base


class Garage(Base):
    """Represents a tenant garage."""

    __tablename__ = "garages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    whatsapp_number: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    customers: Mapped[list["Customer"]] = relationship(back_populates="garage")
    vehicles: Mapped[list["Vehicle"]] = relationship(
        back_populates="garage",
        overlaps="customer,vehicles",
    )
    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="garage",
        overlaps="bookings,vehicle",
    )
    job_cards: Mapped[list["JobCard"]] = relationship(
        back_populates="garage",
        overlaps="booking,job_card",
    )


class Customer(Base):
    """Represents a garage customer."""

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("garage_id", "phone", name="uq_customers_garage_phone"),
        UniqueConstraint("id", "garage_id", name="uq_customers_id_garage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    health_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    vehicles: Mapped[list["Vehicle"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        overlaps="garage,vehicles",
    )

    garage_id: Mapped[int] = mapped_column(
        ForeignKey("garages.id"),
        nullable=False,
        index=True,
    )

    garage: Mapped["Garage"] = relationship(back_populates="customers")


class Vehicle(Base):
    """Represents a vehicle owned by a customer."""

    __tablename__ = "vehicles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "garage_id"],
            ["customers.id", "customers.garage_id"],
            name="fk_vehicles_customer_garage",
        ),
        UniqueConstraint("id", "garage_id", name="uq_vehicles_id_garage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    customer_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    garage_id: Mapped[int] = mapped_column(
        ForeignKey("garages.id"),
        nullable=False,
        index=True,
    )

    vehicle_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    vehicle_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    next_service_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    customer: Mapped["Customer"] = relationship(
        back_populates="vehicles",
        overlaps="garage,vehicles",
    )
    garage: Mapped["Garage"] = relationship(
        back_populates="vehicles",
        overlaps="customer,vehicles",
    )

    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="vehicle",
        cascade="all, delete-orphan",
        overlaps="garage,bookings",
    )


class Booking(Base):
    """Represents a service booking for a specific vehicle."""

    __tablename__ = "bookings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["vehicle_id", "garage_id"],
            ["vehicles.id", "vehicles.garage_id"],
            name="fk_bookings_vehicle_garage",
        ),
        UniqueConstraint("id", "garage_id", name="uq_bookings_id_garage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    vehicle_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    garage_id: Mapped[int] = mapped_column(
        ForeignKey("garages.id"),
        nullable=False,
        index=True,
    )

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

    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    reminder_message_sid: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    delivery_status: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )

    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    vehicle: Mapped["Vehicle"] = relationship(
        back_populates="bookings",
        overlaps="garage,bookings",
    )
    garage: Mapped["Garage"] = relationship(
        back_populates="bookings",
        overlaps="bookings,vehicle",
    )

    job_card: Mapped[Optional["JobCard"]] = relationship(
        back_populates="booking",
        uselist=False,
        cascade="all, delete-orphan",
        overlaps="garage,job_cards",
    )


class JobCard(Base):
    """Represents actual service execution for a booking."""

    __tablename__ = "job_cards"
    __table_args__ = (
        ForeignKeyConstraint(
            ["booking_id", "garage_id"],
            ["bookings.id", "bookings.garage_id"],
            name="fk_job_cards_booking_garage",
        ),
        UniqueConstraint("id", "garage_id", name="uq_job_cards_id_garage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    booking_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        unique=True,
        index=True,
    )
    garage_id: Mapped[int] = mapped_column(
        ForeignKey("garages.id"),
        nullable=False,
        index=True,
    )

    technician_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    work_notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    total_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="IN_PROGRESS",
        server_default=text("'IN_PROGRESS'"),
    )

    booking: Mapped["Booking"] = relationship(
        back_populates="job_card",
        overlaps="garage,job_cards",
    )
    garage: Mapped["Garage"] = relationship(
        back_populates="job_cards",
        overlaps="booking,job_card",
    )
