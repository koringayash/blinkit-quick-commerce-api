from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class OrderStatus:
    """Order lifecycle states (single source of truth for services and analytics)."""
    PLACED = "PLACED"                    # legacy rows created before payments existed
    PENDING_PAYMENT = "PENDING_PAYMENT"  # stock reserved, waiting for payment
    PAID = "PAID"                        # online payment captured
    CONFIRMED = "CONFIRMED"              # Cash on Delivery accepted
    ASSIGNED = "ASSIGNED"                # delivery milestones (synced from delivery service)
    REACHED_DARK_STORE = "REACHED_DARK_STORE"
    PICKED_UP = "PICKED_UP"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"              # cancelled by customer before payment; stock released
    EXPIRED = "EXPIRED"                  # payment window elapsed; stock released

    AWAITING_PAYMENT = frozenset({PLACED, PENDING_PAYMENT})
    IN_TRANSIT = frozenset({ASSIGNED, REACHED_DARK_STORE, PICKED_UP, OUT_FOR_DELIVERY})
    # Orders that count as real sales (money captured or COD committed)
    FULFILLMENT = frozenset({PAID, CONFIRMED, DELIVERED}) | IN_TRANSIT


class Order(Base):
    """One checkout. Holds one or more OrderItems."""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # SET NULL so deleting a saved address doesn't delete order history
    address_id: Mapped[int | None] = mapped_column(
        ForeignKey("addresses.id", ondelete="SET NULL"), nullable=True
    )
    # Dark store fulfilling this order (nullable for legacy/global orders)
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("dark_stores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=OrderStatus.PENDING_PAYMENT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    store = relationship("DarkStore", lazy="selectin")
    delivery = relationship("DeliveryAssignment", back_populates="order", uselist=False, lazy="selectin")
    # Ordered by id so "latest attempt" is deterministic
    payments = relationship(
        "Payment", back_populates="order", cascade="all, delete-orphan", lazy="selectin",
        order_by="Payment.id",
    )

    # Serves the unpaid-order expiry sweep: WHERE status IN (...) AND created_at < cutoff
    __table_args__ = (Index("ix_orders_status_created_at", "status", "created_at"),)


class OrderItem(Base):
    """One product line inside an order."""
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # Price snapshot at purchase time, so history stays correct if the price changes later
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")

    __table_args__ = (CheckConstraint("quantity > 0", name="check_order_item_qty_positive"),)
