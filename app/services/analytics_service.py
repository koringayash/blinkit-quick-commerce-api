"""Business Analytics Service for Blinkit Quick-Commerce Microservice.

Computes real-time KPI metrics for business, growth, and analytics teams:
- Gross Merchandise Value (GMV) & Average Order Value (AOV)
- Payment conversion & method distribution (UPI vs COD vs Cards)
- Order status & delivery turnaround metrics
- Top-selling SKUs and velocity
- Inventory health & stock-out risk detection
"""
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery import DeliveryAssignment
from app.models.item import InventoryItem
from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsSummaryResponse,
    InventoryHealthResponse,
    LowStockItem,
    TopSellingProduct,
)


async def get_analytics_summary(db: AsyncSession) -> AnalyticsSummaryResponse:
    """Computes executive summary KPIs for business analytics."""
    # 1. Revenue & Order totals
    order_metrics = (
        await db.execute(
            select(
                func.count(Order.id).label("total_orders"),
                func.coalesce(func.sum(Order.total), 0).label("total_gmv"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                Order.status.in_(
                                    ["PAID", "CONFIRMED", "DELIVERED", "OUT_FOR_DELIVERY"]
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("paid_orders"),
            )
        )
    ).one()

    total_orders = order_metrics.total_orders or 0
    total_gmv = float(order_metrics.total_gmv or 0.0)
    paid_orders = int(order_metrics.paid_orders or 0)
    aov = round(total_gmv / total_orders, 2) if total_orders > 0 else 0.0

    # 2. Payment method breakdown (from successful payments)
    pay_rows = (
        await db.execute(
            select(Payment.payment_method, func.count(Payment.id))
            .where(Payment.status == "SUCCESS")
            .group_by(Payment.payment_method)
        )
    ).all()
    payment_methods_breakdown = {method: count for method, count in pay_rows}

    # 3. Order status breakdown
    status_rows = (
        await db.execute(select(Order.status, func.count(Order.id)).group_by(Order.status))
    ).all()
    order_status_breakdown = {st: count for st, count in status_rows}

    # 4. Registered customer count (excluding admins)
    customer_count = (
        await db.execute(select(func.count(User.id)).where(User.is_admin.is_(False)))
    ).scalar_one()

    # 5. Active deliveries currently in transit
    active_deliveries = (
        await db.execute(
            select(func.count(DeliveryAssignment.id)).where(
                DeliveryAssignment.status.in_(
                    ["ASSIGNED", "REACHED_DARK_STORE", "PICKED_UP", "OUT_FOR_DELIVERY"]
                )
            )
        )
    ).scalar_one()

    return AnalyticsSummaryResponse(
        total_gmv=round(total_gmv, 2),
        total_orders=total_orders,
        paid_orders=paid_orders,
        average_order_value=aov,
        payment_methods_breakdown=payment_methods_breakdown,
        order_status_breakdown=order_status_breakdown,
        total_customers=customer_count,
        active_deliveries=active_deliveries,
    )


async def get_top_selling_products(
    db: AsyncSession, limit: int = 10
) -> list[TopSellingProduct]:
    """Retrieves top-performing products ranked by volume and revenue."""
    result = await db.execute(
        select(
            InventoryItem.id,
            InventoryItem.sku,
            InventoryItem.name,
            func.sum(OrderItem.quantity).label("units_sold"),
            func.sum(OrderItem.quantity * OrderItem.unit_price).label("revenue"),
        )
        .join(OrderItem, OrderItem.item_id == InventoryItem.id)
        .group_by(InventoryItem.id, InventoryItem.sku, InventoryItem.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
    )

    return [
        TopSellingProduct(
            item_id=row.id,
            sku=row.sku,
            name=row.name,
            total_units_sold=int(row.units_sold),
            total_revenue=round(float(row.revenue), 2),
        )
        for row in result.all()
    ]


async def get_inventory_health(
    db: AsyncSession, threshold: int = 5
) -> InventoryHealthResponse:
    """Detects stock-out risks and calculates total inventory valuation."""
    summary = (
        await db.execute(
            select(
                func.count(InventoryItem.id).label("total_skus"),
                func.coalesce(func.sum(InventoryItem.available_qty), 0).label("total_units"),
                func.coalesce(
                    func.sum(InventoryItem.available_qty * InventoryItem.price), 0
                ).label("total_value"),
                func.coalesce(
                    func.sum(case((InventoryItem.available_qty == 0, 1), else_=0)), 0
                ).label("out_of_stock"),
            )
        )
    ).one()

    low_stock_rows = (
        await db.execute(
            select(InventoryItem)
            .where(InventoryItem.available_qty <= threshold)
            .order_by(InventoryItem.available_qty.asc())
            .limit(25)
        )
    ).scalars().all()

    return InventoryHealthResponse(
        total_skus=summary.total_skus or 0,
        total_inventory_units=int(summary.total_units or 0),
        total_inventory_value=round(float(summary.total_value or 0.0), 2),
        out_of_stock_count=int(summary.out_of_stock or 0),
        low_stock_items=[
            LowStockItem(
                sku=i.sku,
                name=i.name,
                available_qty=i.available_qty,
                price=float(i.price),
            )
            for i in low_stock_rows
        ],
    )

