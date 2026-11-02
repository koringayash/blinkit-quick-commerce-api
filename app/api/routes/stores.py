"""Dark Store & Geo-Serviceability endpoints: store CRUD, GPS/pincode serviceability check, and per-store stock."""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.models import User
from app.schemas.store import (
    DarkStoreCreate,
    DarkStoreResponse,
    DarkStoreUpdate,
    ServiceabilityResponse,
    StoreItemStockResponse,
    StoreStockUpdateRequest,
)
from app.services import store_service

router = APIRouter(prefix="/stores", tags=["stores"])


@router.post("", response_model=DarkStoreResponse, status_code=status.HTTP_201_CREATED)
async def create_store(
    payload: DarkStoreCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Create a new neighborhood Dark Store with GPS coordinates and service radius (admin only)."""
    return await store_service.create_dark_store(db, payload)


@router.get("", response_model=list[DarkStoreResponse])
async def list_stores(
    city: str | None = Query(None, description="Filter dark stores by city (case-insensitive)"),
    pincode: str | None = Query(None, description="Filter dark stores by pincode"),
    active_only: bool = Query(True, description="If True, only return active dark stores"),
    db: AsyncSession = Depends(get_db),
):
    """List Dark Stores (optionally filtered by city, pincode, or active status)."""
    return await store_service.list_dark_stores(
        db, city=city, pincode=pincode, active_only=active_only
    )


@router.get("/serviceability", response_model=ServiceabilityResponse)
async def check_location_serviceability(
    lat: float | None = Query(None, ge=-90.0, le=90.0, description="Customer latitude"),
    lng: float | None = Query(None, ge=-180.0, le=180.0, description="Customer longitude"),
    pincode: str | None = Query(None, pattern=r"^\d{6}$", description="Customer 6-digit pincode (fallback if GPS not provided)"),
    address_id: int | None = Query(None, description="Optional saved Address ID to check serviceability for"),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if a customer's GPS coordinates (`lat`, `lng`), `pincode`, or saved `address_id` is serviceable:
    finds the nearest active Dark Store within its `service_radius_km` (default 3 km) and estimates delivery ETA.
    """
    return await store_service.check_serviceability(
        db, lat=lat, lng=lng, pincode=pincode, address_id=address_id
    )


@router.get("/{store_id}", response_model=DarkStoreResponse)
async def get_store(store_id: int, db: AsyncSession = Depends(get_db)):
    """Get details of a specific Dark Store by ID."""
    return await store_service.get_dark_store(db, store_id)


@router.patch("/{store_id}", response_model=DarkStoreResponse)
async def update_store(
    store_id: int,
    payload: DarkStoreUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Update a Dark Store's radius, base prep minutes, active status, or address (admin only)."""
    return await store_service.update_dark_store(db, store_id, payload)


@router.get("/{store_id}/items", response_model=list[StoreItemStockResponse])
async def list_store_items(
    store_id: int,
    q: str | None = Query(None, max_length=100, description="Search keyword across name, SKU, brand, category"),
    category: str | None = Query(None, description="Filter by category"),
    brand: str | None = Query(None, description="Filter by brand"),
    in_stock_only: bool = Query(False, description="If True, only return items currently in stock at this store"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List catalog items with their stock specific to this Dark Store."""
    return await store_service.list_store_inventory(
        db,
        store_id,
        q=q,
        category=category,
        brand=brand,
        in_stock_only=in_stock_only,
        limit=limit,
        offset=offset,
    )


@router.patch("/{store_id}/items/{sku}/stock", response_model=StoreItemStockResponse)
async def update_store_item_stock(
    store_id: int,
    sku: str,
    payload: StoreStockUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Restock or adjust inventory for a specific SKU at a specific Dark Store (admin only).
    Atomically updates `dark_store_stocks.available_qty` and keeps `inventory_items.available_qty` in sync.
    """
    return await store_service.adjust_store_stock(
        db, store_id, sku, payload.delta_qty, admin
    )

