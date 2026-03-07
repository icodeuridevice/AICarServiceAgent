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
    Text,
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
    users: Mapped[list["User"]] = relationship(back_populates="garage")


class User(Base):
    """Represents an authenticated user (garage owner or staff)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    garage_id: Mapped[int] = mapped_column(
        ForeignKey("garages.id"),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="OWNER",
        server_default=text("'OWNER'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    garage: Mapped["Garage"] = relationship(back_populates="users")


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
    next_service_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_service_mileage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

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


class Escalation(Base):
    """Represents a critical vehicle escalation event."""

    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    garage_id: Mapped[int] = mapped_column(
        ForeignKey("garages.id"),
        nullable=False,
    )
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id"),
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(String, nullable=False)
    health_score: Mapped[int] = mapped_column(Integer, nullable=False)

    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )


class Reminder(Base):
    """Tracks predictive reminders sent to customers for auto-booking."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    garage_id: Mapped[int] = mapped_column(
        ForeignKey("garages.id"),
        nullable=False,
        index=True,
    )
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    service_type: Mapped[str] = mapped_column(String(100), nullable=False)
    predicted_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="SENT",
        server_default=text("'SENT'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    booking_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bookings.id"),
        nullable=True,
    )


class AuditLog(Base):
    """Enterprise audit trail for critical operations."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    garage_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    action_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    extra: Mapped[Optional[dict]] = mapped_column("metadata", type_=String, nullable=True)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)

    phone: Mapped[str] = mapped_column(String(32), index=True)

    garage_id: Mapped[int] = mapped_column(index=True)

    messages_json: Mapped[str] = mapped_column(Text)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
