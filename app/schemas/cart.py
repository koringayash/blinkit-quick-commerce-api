from datetime import datetime

from pydantic import BaseModel, Field


class CartItemSet(BaseModel):
    quantity: int = Field(..., ge=1, le=50, examples=[2])


class CartLine(BaseModel):
    sku: str
    name: str
    unit_price: float
    quantity: int
    line_total: float
    available_qty: int
    in_stock: bool  # False if current stock can't cover the requested quantity
    added_at: datetime


class CartResponse(BaseModel):
    store_id: int | None = None
    store_code: str | None = None
    items: list[CartLine]
    item_count: int
    subtotal: float


class CheckoutRequest(BaseModel):
    address_id: int | None = Field(None, examples=[1])
    store_id: int | None = Field(
        None,
        description="Optional Dark Store ID to fulfill from. If omitted, resolved automatically from address_id.",
        examples=[1],
    )
