"""Pydantic schemas for Dark Stores, Geo-Serviceability checks, and per-store stock."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class DarkStoreCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=30, examples=["BLR-IND-01"])
    name: str = Field(..., min_length=2, max_length=120, examples=["Blinkit Dark Store - Indiranagar 100ft Rd"])
    address: str = Field(..., min_length=5, max_length=255, examples=["100ft Road, HAL 2nd Stage, Indiranagar"])
    city: str = Field(..., min_length=2, max_length=100, examples=["Bengaluru"])
    pincode: str = Field(..., pattern=r"^\d{6}$", examples=["560038"])
    latitude: float = Field(..., ge=-90.0, le=90.0, examples=[12.9784])
    longitude: float = Field(..., ge=-180.0, le=180.0, examples=[77.6408])
    service_radius_km: float = Field(3.0, gt=0.0, le=50.0, examples=[3.0])
    base_prep_minutes: int = Field(3, ge=0, le=60, examples=[3])
    is_active: bool = True


class DarkStoreUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    address: str | None = Field(None, min_length=5, max_length=255)
    city: str | None = Field(None, min_length=2, max_length=100)
    pincode: str | None = Field(None, pattern=r"^\d{6}$")
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
    service_radius_km: float | None = Field(None, gt=0.0, le=50.0)
    base_prep_minutes: int | None = Field(None, ge=0, le=60)
    is_active: bool | None = None


class DarkStoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    address: str
    city: str
    pincode: str
    latitude: float
    longitude: float
    service_radius_km: float
    base_prep_minutes: int
    is_active: bool
    created_at: datetime


class NearbyStoreInfo(BaseModel):
    store: DarkStoreResponse
    distance_km: float
    within_service_radius: bool
    estimated_eta_minutes: int


class ServiceabilityResponse(BaseModel):
    serviceable: bool
    matched_by: str | None = Field(
        None,
        description="How the store was matched: 'gps_radius', 'pincode_fallback', or None",
        examples=["gps_radius"],
    )
    store: DarkStoreResponse | None = None
    distance_km: float | None = Field(None, examples=[1.42])
    eta_minutes: int | None = Field(None, examples=[8])
    message: str
    nearby_stores: list[NearbyStoreInfo] = Field(default_factory=list)


class StoreStockUpdateRequest(BaseModel):
    delta_qty: int = Field(
        ...,
        description="Positive to add stock to this dark store, negative to deduct stock",
        examples=[25],
    )


class StoreItemStockResponse(BaseModel):
    store_id: int
    store_code: str
    item_id: int
    sku: str
    name: str
    category: str | None = None
    brand: str | None = None
    price: float
    store_available_qty: int
    global_available_qty: int

    @computed_field
    @property
    def in_stock(self) -> bool:
        return self.store_available_qty > 0

