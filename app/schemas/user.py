from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRegister(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", examples=["umang@example.com"])
    full_name: str = Field(..., min_length=1, max_length=100, examples=["Umang Koringa"])
    password: str = Field(..., min_length=8, max_length=72)  # bcrypt limit is 72 bytes


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    is_admin: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class FavoriteResponse(BaseModel):
    sku: str
    name: str
    price: float
    available_qty: int
    added_at: datetime


class AddressCreate(BaseModel):
    label: str = Field(..., max_length=50, examples=["Home"])
    line1: str = Field("", max_length=255, examples=["12, MG Road"])
    line2: str | None = Field(None, max_length=255)
    city: str = Field(..., max_length=100, examples=["Bengaluru"])
    pincode: str = Field(..., pattern=r"^\d{6}$", examples=["560001"])
    latitude: float | None = Field(None, ge=-90.0, le=90.0, examples=[12.9716])
    longitude: float | None = Field(None, ge=-180.0, le=180.0, examples=[77.5946])
    is_default: bool = False


class AddressResponse(AddressCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
