"""Payment endpoints: initiate payment, list payments, simulate success/failure, and gateway webhooks."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import PAYMENT_SANDBOX_ENABLED
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.payment import Payment
from app.models.user import User
from app.schemas.payment import (
    PaymentInitiateRequest,
    PaymentInitiateResponse,
    PaymentResponse,
    PaymentSimulateSuccessRequest,
)
from app.services import payment_service

logger = get_logger("app.payments.routes")
router = APIRouter(tags=["payments"])


def require_payment_sandbox() -> None:
    """Simulation endpoints exist only with the MOCK gateway; with a real gateway they 404."""
    if not PAYMENT_SANDBOX_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


async def _get_owned_payment(db: AsyncSession, user: User, order_id: int, payment_id: int) -> Payment:
    payment = await db.get(Payment, payment_id)
    if not payment or payment.order_id != order_id or payment.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment


@router.post("/me/orders/{order_id}/payments", response_model=PaymentInitiateResponse)
async def initiate_order_payment(
    order_id: int,
    payload: PaymentInitiateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate payment for an order.
    - payment_method = "COD": instantly confirms order and dispatches delivery.
    - payment_method = "UPI", "CARD", or "WALLET": creates payment gateway order (Razorpay / Mock) and returns payment token.
    """
    return await payment_service.initiate_payment(db, user, order_id, payload.payment_method)


@router.get("/me/orders/{order_id}/payments", response_model=list[PaymentResponse])
async def list_order_payments(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all payment attempts and status for an order."""
    return await payment_service.list_payments_for_order(db, user, order_id)


@router.post(
    "/me/orders/{order_id}/payments/{payment_id}/simulate-success",
    response_model=PaymentResponse,
    dependencies=[Depends(require_payment_sandbox)],
)
async def simulate_payment_success(
    order_id: int,
    payment_id: int,
    payload: PaymentSimulateSuccessRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sandbox endpoint (MOCK gateway only): simulates successful payment completion from the gateway.
    Marks order as PAID and dispatches delivery partner without requiring real bank credentials.
    """
    await _get_owned_payment(db, user, order_id, payment_id)
    gateway_payment_id = payload.gateway_payment_id if payload else None
    return await payment_service.confirm_payment_success(db, payment_id, gateway_payment_id)


@router.post(
    "/me/orders/{order_id}/payments/{payment_id}/simulate-failure",
    response_model=PaymentResponse,
    dependencies=[Depends(require_payment_sandbox)],
)
async def simulate_payment_failure(
    order_id: int,
    payment_id: int,
    reason: str = Query("Card declined / Insufficient funds", max_length=255),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sandbox endpoint (MOCK gateway only): simulates a declined payment.
    The payment becomes FAILED; the order keeps its reserved stock so the customer can retry
    until it is cancelled or the payment window expires.
    """
    await _get_owned_payment(db, user, order_id, payment_id)
    return await payment_service.handle_payment_failure(db, payment_id, reason)


@router.post("/payments/webhook")
async def payment_gateway_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    External payment gateway webhook endpoint (Razorpay/Mock).
    Cryptographically verifies the HMAC signature (X-Razorpay-Signature) and updates order status.
    Returns 2xx for handled/ignored events; unexpected errors return 5xx so the gateway retries.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    if not payment_service.gateway.verify_webhook_signature(raw_body, signature):
        logger.warning("Rejected payment webhook with missing/invalid signature")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    try:
        event = json.loads(raw_body)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload")

    event_type = event.get("event")
    entity = event.get("payload", {}).get("payment", {}).get("entity", {})
    gateway_order_id = entity.get("order_id")
    gateway_payment_id = entity.get("id")

    if event_type not in {"payment.captured", "payment.failed"} or not gateway_order_id:
        return {"status": "ignored", "event": event_type}

    payment = (
        await db.execute(select(Payment).where(Payment.gateway_order_id == gateway_order_id))
    ).scalar_one_or_none()
    if not payment:
        logger.warning(
            f"Webhook for unknown gateway order {gateway_order_id}",
            extra={"gateway_order_id": gateway_order_id, "event": event_type},
        )
        return {"status": "ignored", "event": event_type}

    try:
        if event_type == "payment.captured":
            await payment_service.confirm_payment_success(db, payment.id, gateway_payment_id)
        else:
            reason = entity.get("error_description") or "Payment failed via gateway"
            await payment_service.handle_payment_failure(db, payment.id, reason)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            # Out-of-order / stale event (e.g. "failed" arriving after "captured") - safe to ignore
            logger.info(f"Ignored stale webhook {event_type} for payment {payment.id}: {exc.detail}")
            return {"status": "ignored", "event": event_type}
        raise

    return {"status": "ok", "event": event_type}
