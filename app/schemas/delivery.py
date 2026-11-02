from datetime import datetime
from pydantic import BaseModel, Field


class RiderInfo(BaseModel):
    name: str = Field(..., examples=["Ramesh Kumar"])
    phone: str = Field(..., examples=["+91-9876543210"])
    vehicle_type: str = Field(..., examples=["Electric Scooter"])


class LocationPoint(BaseModel):
    latitude: float = Field(..., examples=[12.9716])
    longitude: float = Field(..., examples=[77.5946])


class DeliveryStatusSnapshot(BaseModel):
    order_id: int
    tracking_id: str
    status: str = Field(..., description="ASSIGNED, REACHED_DARK_STORE, PICKED_UP, OUT_FOR_DELIVERY, DELIVERED")
    partner_name: str
    rider: RiderInfo
    pickup_address: str
    delivery_address: str
    current_location: LocationPoint
    pickup_location: LocationPoint
    delivery_location: LocationPoint
    eta_minutes: int
    last_updated_at: datetime

