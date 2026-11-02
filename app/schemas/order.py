from datetime import datetime
from pydantic import BaseModel, Field


class OrderLineResponse(BaseModel):
    sku: str
    name: str
    quantity: int
    unit_price: float
    line_total: float


class OrderResponse(BaseModel):
    id: int
    status: str
    address_id: int | None
    store_id: int | None = None
    store_code: str | None = Field(None, examples=["BLR-IND-01"])
    store_name: str | None = Field(None, examples=["Blinkit Dark Store - Indiranagar 100ft Rd"])
    total: float
    created_at: datetime
    delivery_status: str | None = Field(None, examples=["OUT_FOR_DELIVERY"])
    tracking_id: str | None = Field(None, examples=["TRK-QCK-101-5821"])
    delivery_address: str | None = Field(None, examples=["12, MG Road, Bengaluru - 560001"])
    payment_status: str | None = Field(None, examples=["SUCCESS"])
    payment_method: str | None = Field(None, examples=["UPI"])
    items: list[OrderLineResponse]


class ReorderResponse(BaseModel):
    order_id: int
    items_added_to_cart: int
    out_of_stock_skus: list[str]
    message: str
