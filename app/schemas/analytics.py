from pydantic import BaseModel, Field


class AnalyticsSummaryResponse(BaseModel):
    total_gmv: float = Field(..., description="Total Gross Merchandise Value (Revenue) from orders")
    total_orders: int
    paid_orders: int
    average_order_value: float = Field(..., description="Average order value (AOV)")
    payment_methods_breakdown: dict[str, int] = Field(
        ..., description="Count of payments by method (UPI, COD, CARD, WALLET)"
    )
    order_status_breakdown: dict[str, int] = Field(
        ..., description="Count of orders by status (PLACED, PAID, DELIVERED, etc.)"
    )
    total_customers: int
    active_deliveries: int


class TopSellingProduct(BaseModel):
    item_id: int
    sku: str
    name: str
    total_units_sold: int
    total_revenue: float


class LowStockItem(BaseModel):
    sku: str
    name: str
    available_qty: int
    price: float


class InventoryHealthResponse(BaseModel):
    total_skus: int
    total_inventory_units: int
    total_inventory_value: float
    out_of_stock_count: int
    low_stock_items: list[LowStockItem]

