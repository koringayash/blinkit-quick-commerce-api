from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DeliveryAssignment(Base):
    """
    Persistent milestone record linking an Order to a 3rd-party delivery partner assignment.
    High-frequency GPS ticks stay in memory/cache; only major milestones are committed here.
    """
    __tablename__ = "delivery_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), unique=True, index=True
    )
    tracking_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    partner_name: Mapped[str] = mapped_column(String(50), default="QuickLogistics")
    rider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rider_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(50), default="Electric Scooter")
    status: Mapped[str] = mapped_column(String(30), default="ASSIGNED")
    pickup_address: Mapped[str] = mapped_column(String(255), nullable=False)
    delivery_address: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order = relationship("Order", back_populates="delivery")

