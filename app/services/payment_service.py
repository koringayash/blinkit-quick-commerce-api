"""Payment service for Blinkit microservice.

Supports:
- Unified gateway interface (PaymentGateway) with HMAC-SHA256 webhook verification
- Mock payment gateway for local development and test automation
- Razorpay adapter (webhook verification implemented; Orders/Refunds API calls still to be wired)
- Cash on Delivery (COD) instant order confirmation
- Delivery partner dispatch only after payment succeeds / COD is chosen

State machine (all transitions run under row locks: order row first, then payment row):
    order PENDING_PAYMENT --COD--------------------> CONFIRMED  (+ dispatch)
    order PENDING_PAYMENT --online, captured-------> PAID       (+ dispatch)
    payment PENDING --declined--> FAILED   (order stays PENDING_PAYMENT so the customer can retry;
                                            reserved stock is released by cancel or expiry)
    payment captured for an order that is no longer payable (expired/cancelled/superseded) -> REFUNDED
"""
import asyncio
import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
import uuid
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import (
    PAYMENT_GATEWAY,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET,
)
from app.core.logging import get_logger
from app.core.tasks import spawn
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.store import DarkStore
from app.models.user import Address, User
from app.schemas.payment import PaymentInitiateResponse
from app.services.delivery_service import dispatch_order_delivery
from app.services.order_service import lock_order_for_user

logger = get_logger("app.payments")


def _to_minor_units(amount: Decimal | float) -> int:
    """INR -> paise (1 INR = 100 paise), computed in Decimal to avoid float rounding."""
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1")))


class PaymentGateway(ABC):
    """Abstract interface for payment gateway providers (Razorpay, Cashfree, Mock)."""

    name: str

    def __init__(self, webhook_secret: str):
        self.webhook_secret = webhook_secret

    @abstractmethod
    async def create_payment_order(
        self, amount: Decimal, currency: str, receipt: str, notes: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a payment order on the gateway."""

    @abstractmethod
    async def process_refund(self, gateway_payment_id: str, amount: Decimal) -> dict[str, Any]:
        """Process a refund for a captured payment."""

    def verify_webhook_signature(self, raw_body: bytes, signature: str | None) -> bool:
        """Cryptographically verify the HMAC-SHA256 signature of an incoming webhook body."""
        if not signature:
            return False
        expected = hmac.new(self.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class MockPaymentGateway(PaymentGateway):
    """
    Development simulator that mimics gateway order creation and refunds without credentials.
    Webhooks are still HMAC-verified (with RAZORPAY_WEBHOOK_SECRET) so nobody can forge a payment.
    """

    name = "MOCK"

    async def create_payment_order(
        self, amount: Decimal, currency: str, receipt: str, notes: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "id": f"order_mock_{uuid.uuid4().hex[:12]}",
            "amount": _to_minor_units(amount),
            "currency": currency,
            "receipt": receipt,
            "status": "created",
            "payment_token": f"tok_mock_{uuid.uuid4().hex[:16]}",
        }

    async def process_refund(self, gateway_payment_id: str, amount: Decimal) -> dict[str, Any]:
        return {
            "id": f"rfnd_mock_{uuid.uuid4().hex[:12]}",
            "payment_id": gateway_payment_id,
            "amount": _to_minor_units(amount),
            "status": "processed",
        }


class RazorpayPaymentGateway(PaymentGateway):
    """
    Production Razorpay adapter using Razorpay's REST API v1 (`https://api.razorpay.com/v1`)
    with HTTP Basic Auth (`key_id:key_secret`) and HMAC-SHA256 webhook signature verification.
    """

    name = "RAZORPAY"
    BASE_URL = "https://api.razorpay.com/v1"

    def __init__(self, key_id: str, key_secret: str, webhook_secret: str):
        super().__init__(webhook_secret)
        self.key_id = key_id
        self.key_secret = key_secret

    def _request_sync(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.key_id or not self.key_secret or self.key_id == "rzp_test_mock_key":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Live Razorpay credentials (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET) are not configured",
            )
        creds = base64.b64encode(f"{self.key_id}:{self.key_secret}".encode("utf-8")).decode("ascii")
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            logger.error(
                f"Razorpay API HTTP {exc.code} on {path}: {err_body}",
                extra={"status_code": exc.code, "path": path},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Payment gateway error ({exc.code})",
            ) from exc
        except urllib.error.URLError as exc:
            logger.error(f"Razorpay API network error on {path}: {exc}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to reach Razorpay payment gateway",
            ) from exc

    async def create_payment_order(
        self, amount: Decimal, currency: str, receipt: str, notes: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = {
            "amount": _to_minor_units(amount),
            "currency": currency,
            "receipt": receipt,
            "notes": notes or {},
        }
        res = await asyncio.to_thread(self._request_sync, "POST", "/orders", payload)
        res.setdefault("payment_token", self.key_id)
        return res

    async def process_refund(self, gateway_payment_id: str, amount: Decimal) -> dict[str, Any]:
        payload = {"amount": _to_minor_units(amount)}
        return await asyncio.to_thread(
            self._request_sync, "POST", f"/payments/{gateway_payment_id}/refund", payload
        )


def get_payment_gateway() -> PaymentGateway:
    if PAYMENT_GATEWAY == "RAZORPAY":
        return RazorpayPaymentGateway(
            key_id=RAZORPAY_KEY_ID,
            key_secret=RAZORPAY_KEY_SECRET,
            webhook_secret=RAZORPAY_WEBHOOK_SECRET,
        )
    return MockPaymentGateway(webhook_secret=RAZORPAY_WEBHOOK_SECRET)


gateway: PaymentGateway = get_payment_gateway()


async def initiate_payment(
    db: AsyncSession, user: User, order_id: int, payment_method: str
) -> PaymentInitiateResponse:
    """
    Initiate payment for an order.
    Supports Cash on Delivery (COD) instant placement or Online Gateway order creation (UPI/CARD/WALLET).
    """
    order = await lock_order_for_user(db, user, order_id)

    if order.status not in OrderStatus.AWAITING_PAYMENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order is {order.status}; payment can only be initiated for unpaid orders",
        )

    # A new attempt supersedes any earlier pending one (e.g. customer switches UPI -> COD).
    # If the old attempt is captured later anyway, confirm_payment_success refunds it.
    for previous in order.payments:
        if previous.status == PaymentStatus.PENDING:
            previous.status = PaymentStatus.FAILED
            previous.error_reason = "Superseded by a new payment attempt"

    # 1. Cash on Delivery (COD) Flow
    if payment_method == "COD":
        payment = Payment(
            order_id=order.id,
            user_id=user.id,
            amount=order.total,
            currency="INR",
            payment_method="COD",
            status=PaymentStatus.SUCCESS,
            gateway_name="COD",
            gateway_order_id=f"cod_{order.id}",
            gateway_payment_id=f"cod_pay_{order.id}",
        )
        db.add(payment)
        order.status = OrderStatus.CONFIRMED
        await db.commit()
        await db.refresh(payment)

        await _dispatch_delivery(db, order)
        logger.info(
            f"COD payment confirmed for order {order.id} (total: Rs. {order.total})",
            extra={"order_id": order.id, "payment_method": "COD", "total": order.total},
        )
        return PaymentInitiateResponse(
            payment_id=payment.id,
            order_id=order.id,
            amount=float(order.total),
            currency="INR",
            payment_method="COD",
            status=PaymentStatus.SUCCESS,
            gateway_name="COD",
            gateway_order_id=payment.gateway_order_id,
            payment_token=None,
            message="Order confirmed with Cash on Delivery. Rider is being assigned.",
        )

    # 2. Online Payment Gateway Flow (UPI, CARD, WALLET)
    gateway_order = await gateway.create_payment_order(
        amount=Decimal(order.total),
        currency="INR",
        receipt=f"blinkit_ord_{order.id}",
        notes={"user_id": user.id, "order_id": order.id},
    )

    payment = Payment(
        order_id=order.id,
        user_id=user.id,
        amount=order.total,
        currency="INR",
        payment_method=payment_method,
        status=PaymentStatus.PENDING,
        gateway_name=gateway.name,
        gateway_order_id=gateway_order["id"],
    )
    db.add(payment)
    order.status = OrderStatus.PENDING_PAYMENT
    await db.commit()
    await db.refresh(payment)

    logger.info(
        f"Initiated {payment_method} payment for order {order.id}: gateway_order={gateway_order['id']}",
        extra={"order_id": order.id, "payment_id": payment.id, "gateway_order": gateway_order["id"]},
    )
    return PaymentInitiateResponse(
        payment_id=payment.id,
        order_id=order.id,
        amount=float(order.total),
        currency="INR",
        payment_method=payment_method,
        status=PaymentStatus.PENDING,
        gateway_name=gateway.name,
        gateway_order_id=gateway_order["id"],
        payment_token=gateway_order.get("payment_token"),
        message=f"{payment_method} payment initiated. Complete payment using gateway token.",
    )


async def _lock_payment_and_order(db: AsyncSession, payment_id: int) -> tuple[Payment, Order]:
    """Lock the order row first, then the payment row (same order as cancel/expiry paths)."""
    payment = await db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    order = (
        await db.execute(
            select(Order)
            .where(Order.id == payment.order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    payment = (
        await db.execute(
            select(Payment)
            .where(Payment.id == payment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return payment, order


async def confirm_payment_success(
    db: AsyncSession, payment_id: int, gateway_payment_id: str | None = None
) -> Payment:
    """
    Marks payment as SUCCESS, advances order status to PAID, and dispatches delivery partner.
    Idempotent for webhook retries. Money captured for an order that can no longer be fulfilled
    (expired, cancelled, or a superseded attempt) is refunded automatically.
    """
    payment, order = await _lock_payment_and_order(db, payment_id)

    if payment.status in (PaymentStatus.SUCCESS, PaymentStatus.REFUNDED):
        return payment  # duplicate webhook delivery

    payment.gateway_payment_id = gateway_payment_id or f"pay_mock_{uuid.uuid4().hex[:10]}"

    if payment.status == PaymentStatus.PENDING and order.status in OrderStatus.AWAITING_PAYMENT:
        payment.status = PaymentStatus.SUCCESS
        order.status = OrderStatus.PAID
        await db.commit()
        await db.refresh(payment)

        await _dispatch_delivery(db, order)
        logger.info(
            f"Payment {payment.id} confirmed SUCCESS for order {payment.order_id}",
            extra={"payment_id": payment.id, "order_id": payment.order_id, "amount": payment.amount},
        )
        return payment

    # Captured, but the order isn't payable any more -> give the money back
    refund = await gateway.process_refund(payment.gateway_payment_id, Decimal(payment.amount))
    payment.status = PaymentStatus.REFUNDED
    payment.error_reason = f"Auto-refunded ({refund['id']}): order was {order.status} when payment was captured"
    await db.commit()
    await db.refresh(payment)
    logger.warning(
        f"Payment {payment.id} captured for non-payable order {order.id} ({order.status}); refunded",
        extra={"payment_id": payment.id, "order_id": order.id, "order_status": order.status},
    )
    return payment


async def handle_payment_failure(db: AsyncSession, payment_id: int, error_reason: str) -> Payment:
    """
    Marks a PENDING payment as FAILED. The order stays PENDING_PAYMENT with its stock reserved so
    the customer can retry (UPI -> Card -> COD); stock is released on cancel or when the payment
    window expires. Failing a payment that already succeeded is rejected.
    """
    payment, _order = await _lock_payment_and_order(db, payment_id)

    if payment.status == PaymentStatus.FAILED:
        return payment
    if payment.status != PaymentStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Payment is already {payment.status} and cannot be marked as failed",
        )

    payment.status = PaymentStatus.FAILED
    payment.error_reason = error_reason[:255]
    await db.commit()
    await db.refresh(payment)

    logger.warning(
        f"Payment {payment.id} FAILED for order {payment.order_id}: {error_reason}",
        extra={"payment_id": payment.id, "order_id": payment.order_id, "reason": error_reason},
    )
    return payment


async def list_payments_for_order(db: AsyncSession, user: User, order_id: int) -> list[Payment]:
    """Retrieve all payment records for an order."""
    owns = await db.scalar(select(Order.id).where(Order.id == order_id, Order.user_id == user.id))
    if owns is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    res = await db.execute(
        select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc(), Payment.id.desc())
    )
    return list(res.scalars().all())


async def _dispatch_delivery(db: AsyncSession, order: Order) -> None:
    delivery_address = "Customer Delivery Address"
    delivery_lat: float | None = None
    delivery_lng: float | None = None
    if order.address_id:
        addr = await db.get(Address, order.address_id)
        if addr:
            delivery_address = f"{addr.line1}, {addr.city} - {addr.pincode}"
            delivery_lat = addr.latitude
            delivery_lng = addr.longitude

    pickup_address: str | None = None
    pickup_lat: float | None = None
    pickup_lng: float | None = None
    if order.store_id:
        store = order.store or await db.get(DarkStore, order.store_id)
        if store:
            pickup_address = f"{store.name}, {store.address}, {store.city} - {store.pincode}"
            pickup_lat = store.latitude
            pickup_lng = store.longitude

    spawn(
        dispatch_order_delivery(
            order.id,
            delivery_address,
            pickup_address=pickup_address,
            pickup_lat=pickup_lat,
            pickup_lng=pickup_lng,
            delivery_lat=delivery_lat,
            delivery_lng=delivery_lng,
        ),
        name=f"dispatch-order-{order.id}",
    )
