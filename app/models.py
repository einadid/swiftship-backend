"""SQLAlchemy models: User, Service, Parcel, PasswordResetToken."""
import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    phone = Column(String(20), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(10), nullable=False, default="user")  # "user" | "admin"
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    parcels = relationship("Parcel", back_populates="owner", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    base_price = Column(Float, nullable=False, default=0.0)  # fixed fee per shipment
    price_per_kg = Column(Float, nullable=False, default=0.0)
    eta_days = Column(Integer, nullable=False, default=3)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    parcels = relationship("Parcel", back_populates="service")


class Parcel(Base):
    __tablename__ = "parcels"

    id = Column(Integer, primary_key=True, index=True)
    tracking_number = Column(String(30), unique=True, index=True, nullable=False)
    sender_name = Column(String(100), nullable=False)
    sender_phone = Column(String(20), nullable=False)
    recipient_name = Column(String(100), nullable=False)
    recipient_phone = Column(String(20), nullable=False)
    pickup_address = Column(Text, nullable=False)
    delivery_address = Column(Text, nullable=False)
    weight_kg = Column(Float, nullable=False)
    price = Column(Float, nullable=False, default=0.0)
    notes = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    service = relationship("Service", back_populates="parcels")
    owner = relationship("User", back_populates="parcels")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(100), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User")


# Allowed parcel lifecycle statuses
PARCEL_STATUSES = [
    "pending",
    "picked_up",
    "in_transit",
    "out_for_delivery",
    "delivered",
    "cancelled",
]
