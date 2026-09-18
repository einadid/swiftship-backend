"""Pydantic schemas (request/response validation)."""
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import PARCEL_STATUSES


def validate_password_strength(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"\d", v):
        raise ValueError("Password must contain at least one number")
    return v


def validate_phone(v: str) -> str:
    v = v.strip()
    if not re.fullmatch(r"(\+?88)?01[3-9]\d{8}", v.replace(" ", "")):
        raise ValueError("Invalid Bangladeshi phone number (e.g. 01712345678)")
    return v


# ---------- Auth ----------
class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str
    password: str

    @field_validator("password")
    @classmethod
    def _pw(cls, v):
        return validate_password_strength(v)

    @field_validator("phone")
    @classmethod
    def _ph(cls, v):
        return validate_phone(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v):
        return validate_password_strength(v)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v):
        return validate_password_strength(v)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: EmailStr
    phone: str
    role: str
    is_active: bool
    created_at: datetime


class LoginResponse(BaseModel):
    user: UserOut
    tokens: TokenPair


# ---------- Services ----------
class ServiceBase(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    base_price: float = Field(ge=0)
    price_per_kg: float = Field(ge=0)
    eta_days: int = Field(ge=0, le=90)
    is_active: bool = True


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    base_price: float | None = Field(default=None, ge=0)
    price_per_kg: float | None = Field(default=None, ge=0)
    eta_days: int | None = Field(default=None, ge=0, le=90)
    is_active: bool | None = None


class ServiceOut(ServiceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ---------- Parcels ----------
class ParcelBase(BaseModel):
    sender_name: str = Field(min_length=2, max_length=100)
    sender_phone: str
    recipient_name: str = Field(min_length=2, max_length=100)
    recipient_phone: str
    pickup_address: str = Field(min_length=5, max_length=500)
    delivery_address: str = Field(min_length=5, max_length=500)
    weight_kg: float = Field(gt=0, le=500)
    notes: str | None = Field(default=None, max_length=1000)
    service_id: int

    @field_validator("sender_phone", "recipient_phone")
    @classmethod
    def _ph(cls, v):
        return validate_phone(v)


class ParcelCreate(ParcelBase):
    pass


class ParcelUpdate(BaseModel):
    sender_name: str | None = Field(default=None, min_length=2, max_length=100)
    sender_phone: str | None = None
    recipient_name: str | None = Field(default=None, min_length=2, max_length=100)
    recipient_phone: str | None = None
    pickup_address: str | None = Field(default=None, min_length=5, max_length=500)
    delivery_address: str | None = Field(default=None, min_length=5, max_length=500)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    notes: str | None = Field(default=None, max_length=1000)
    service_id: int | None = None
    status: str | None = None  # admin only

    @field_validator("sender_phone", "recipient_phone")
    @classmethod
    def _ph(cls, v):
        return validate_phone(v) if v is not None else v

    @field_validator("status")
    @classmethod
    def _st(cls, v):
        if v is not None and v not in PARCEL_STATUSES:
            raise ValueError(f"Invalid status. Allowed: {', '.join(PARCEL_STATUSES)}")
        return v


class StatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _st(cls, v):
        if v not in PARCEL_STATUSES:
            raise ValueError(f"Invalid status. Allowed: {', '.join(PARCEL_STATUSES)}")
        return v


class ParcelOut(ParcelBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tracking_number: str
    price: float
    status: str
    owner_id: int
    created_at: datetime
    updated_at: datetime
    service: ServiceOut
    owner: UserOut


class ParcelList(BaseModel):
    items: list[ParcelOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class ParcelSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    total_spent: float
    delivered: int
    active: int  # anything not delivered/cancelled


class AdminStats(BaseModel):
    total_parcels: int
    total_revenue: float
    total_users: int
    total_services: int
    active_parcels: int
    by_status: dict[str, int]
    recent_parcels: list[ParcelOut]


class TrackOut(BaseModel):
    tracking_number: str
    status: str
    status_label: str
    sender_name: str
    recipient_name: str
    pickup_address: str
    delivery_address: str
    weight_kg: float
    price: float
    service_name: str
    booked_at: datetime
    last_updated: datetime
    history: list[dict]


class UserActiveUpdate(BaseModel):
    is_active: bool


class AdminSetPassword(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v):
        return validate_password_strength(v)


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    page_size: int
    total_pages: int
