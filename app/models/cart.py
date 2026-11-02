from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CartItem(Base):
    """
    A product in a user's cart. No price is stored: the cart always shows the live price,
    and the price is only frozen at checkout (OrderItem.unit_price).
    Stock is NOT reserved here; it is deducted at checkout.
    """
    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_user_cart_item"),
        CheckConstraint("quantity > 0", name="check_cart_qty_positive"),
    )
