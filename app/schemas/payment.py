from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class PaymentInitiateRequest(BaseModel):
    payment_method: str = Field(
        ...,
        pattern="^(UPI|CARD|COD|WALLET)$",
        description="Payment mode: UPI, CARD, COD, or WALLET",
        examples=["UPI"],
    )


class PaymentInitiateResponse(BaseModel):
    payment_id: int
    order_id: int
    amount: float
    currency: str
    payment_method: str
    status: str
    gateway_name: str
    gateway_order_id: str | None = None
    payment_token: str | None = None
    message: str


class PaymentSimulateSuccessRequest(BaseModel):
    gateway_payment_id: str | None = Field(None, examples=["pay_mock_12345678"])


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    user_id: int
    amount: float
    currency: str
    payment_method: str
    status: str
    gateway_name: str
    gateway_order_id: str | None = None
    gateway_payment_id: str | None = None
    error_reason: str | None = None
    created_at: datetime
    updated_at: datetime

