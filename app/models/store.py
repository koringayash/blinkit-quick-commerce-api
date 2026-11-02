"""Dark Store and per-store inventory stock models."""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DarkStore(Base):
    """Neighborhood fulfillment micro-warehouse (Dark Store) with GPS coordinates & service radius."""

    __tablename__ = "dark_stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    pincode: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    service_radius_km: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    base_prep_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stocks: Mapped[list["DarkStoreStock"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("service_radius_km > 0", name="check_dark_store_radius_positive"),
        CheckConstraint("base_prep_minutes >= 0", name="check_dark_store_prep_non_negative"),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="check_dark_store_lat_range"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="check_dark_store_lng_range"),
    )


class DarkStoreStock(Base):
    """Per-store inventory count for a specific product (SKU)."""

    __tablename__ = "dark_store_stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("dark_stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    available_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    store: Mapped[DarkStore] = relationship(back_populates="stocks")

    __table_args__ = (
        UniqueConstraint("store_id", "item_id", name="uq_dark_store_item_stock"),
        CheckConstraint("available_qty >= 0", name="check_dark_store_stock_non_negative"),
        Index("ix_dark_store_stocks_store_item", "store_id", "item_id"),
    )

