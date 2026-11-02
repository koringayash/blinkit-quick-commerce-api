"""Admin Business Analytics routes for sales, revenue, payment conversion, and inventory health."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsSummaryResponse,
    InventoryHealthResponse,
    TopSellingProduct,
)
from app.services import analytics_service

router = APIRouter(prefix="/admin/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Executive Analytics Summary: Gross Merchandise Value (GMV), Total Orders,
    Average Order Value (AOV), Payment distribution (UPI vs COD), and Active Deliveries.
    (Admin only)
    """
    return await analytics_service.get_analytics_summary(db)


@router.get("/top-selling", response_model=list[TopSellingProduct])
async def get_top_selling_products(
    limit: int = 10,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Top-Selling Products: Ranked by unit velocity and generated revenue.
    (Admin only)
    """
    return await analytics_service.get_top_selling_products(db, limit=limit)


@router.get("/inventory-health", response_model=InventoryHealthResponse)
async def get_inventory_health(
    threshold: int = 5,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Inventory Health & Valuation: Total catalog valuation, total stock units,
    out-of-stock items, and low-stock replenishment warnings.
    (Admin only)
    """
    return await analytics_service.get_inventory_health(db, threshold=threshold)

