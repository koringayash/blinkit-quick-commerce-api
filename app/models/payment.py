from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PaymentStatus:
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class Payment(Base):
    """
    Payment transaction record for an Order.
    Tracks gateway order reference, payment method (UPI, CARD, COD, WALLET),
    and status transitions (PENDING -> SUCCESS / FAILED / REFUNDED).
    """
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)  # UPI, CARD, COD, WALLET
    status: Mapped[str] = mapped_column(String(30), default=PaymentStatus.PENDING, nullable=False)
    gateway_name: Mapped[str] = mapped_column(String(50), default="MOCK", nullable=False)  # RAZORPAY, MOCK, COD
    gateway_order_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    gateway_payment_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    order = relationship("Order", back_populates="payments")
