"""Dark Store management, Haversine geo-serviceability, ETA estimation, and per-store stock logic."""
import math
from collections.abc import Sequence

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Address, DarkStore, DarkStoreStock, InventoryItem, User
from app.schemas.store import (
    DarkStoreCreate,
    DarkStoreResponse,
    DarkStoreUpdate,
    NearbyStoreInfo,
    ServiceabilityResponse,
    StoreItemStockResponse,
)

logger = get_logger("app.stores")

EARTH_RADIUS_KM = 6371.0
MINUTES_PER_KM = 3.0  # ~20 km/h urban two-wheeler average speed


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate great-circle distance in kilometers between two GPS coordinates
    using the Haversine formula.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_KM * c


def estimate_eta_minutes(distance_km: float, base_prep_minutes: int = 3) -> int:
    """
    Estimate delivery ETA in minutes:
        ETA = base_prep_minutes (picking & packing) + ceil(distance_km * 3.0 min/km).
    Minimum ETA is at least max(5, base_prep_minutes + 1) minutes.
    """
    travel_minutes = math.ceil(max(0.0, distance_km) * MINUTES_PER_KM)
    return max(5, int(base_prep_minutes) + max(1, travel_minutes))


async def create_dark_store(db: AsyncSession, payload: DarkStoreCreate) -> DarkStore:
    """Create a new neighborhood Dark Store (admin only, race-safe on store code)."""
    data = payload.model_dump()
    data["code"] = data["code"].strip().upper()

    stmt = (
        pg_insert(DarkStore)
        .values(**data)
        .on_conflict_do_nothing(index_elements=[DarkStore.code])
        .returning(DarkStore)
    )
    store = (await db.execute(stmt)).scalar_one_or_none()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dark store with code '{data['code']}' already exists",
        )
    await db.commit()
    logger.info(
        f"Created dark store {store.code} ({store.name}) at ({store.latitude}, {store.longitude})",
        extra={"store_id": store.id, "code": store.code, "city": store.city, "pincode": store.pincode},
    )
    return store


async def get_dark_store(
    db: AsyncSession, store_id: int, *, require_active: bool = False
) -> DarkStore:
    store = await db.get(DarkStore, store_id)
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dark store not found")
    if require_active and not store.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dark store '{store.code}' ({store.name}) is currently inactive",
        )
    return store


async def list_dark_stores(
    db: AsyncSession,
    *,
    city: str | None = None,
    pincode: str | None = None,
    active_only: bool = True,
) -> list[DarkStore]:
    """List dark stores with optional city, pincode, and active filters."""
    stmt = select(DarkStore)
    if active_only:
        stmt = stmt.where(DarkStore.is_active.is_(True))
    if city and city.strip():
        stmt = stmt.where(func.lower(DarkStore.city) == city.strip().lower())
    if pincode and pincode.strip():
        stmt = stmt.where(DarkStore.pincode == pincode.strip())
    stmt = stmt.order_by(DarkStore.city.asc(), DarkStore.name.asc(), DarkStore.id.asc())
    return list((await db.execute(stmt)).scalars().all())


async def update_dark_store(
    db: AsyncSession, store_id: int, payload: DarkStoreUpdate
) -> DarkStore:
    """Update a dark store's configuration (radius, prep time, active status, address, etc.)."""
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided for update",
        )
    stmt = select(DarkStore).where(DarkStore.id == store_id).with_for_update()
    store = (await db.execute(stmt)).scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dark store not found")

    for field, value in updates.items():
        setattr(store, field, value)

    await db.commit()
    await db.refresh(store)
    logger.info(
        f"Updated dark store {store.code} (id={store.id})",
        extra={"store_id": store.id, "updated_fields": list(updates.keys())},
    )
    return store


async def check_serviceability(
    db: AsyncSession,
    *,
    lat: float | None = None,
    lng: float | None = None,
    pincode: str | None = None,
    address_id: int | None = None,
    user: User | None = None,
) -> ServiceabilityResponse:
    """
    Given customer GPS coordinates (`lat`, `lng`), a `pincode`, or a saved `address_id`:
    1. Finds all active dark stores.
    2. If coordinates are available, computes Haversine distance to every active dark store,
       picks the nearest store where `distance_km <= store.service_radius_km`, and calculates ETA.
    3. If only a `pincode` is available (no coordinates), falls back to matching an active dark store
       serving that pincode.
    """
    if (lat is None) ^ (lng is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'lat' and 'lng' must be provided together",
        )

    # Resolve from saved address if address_id is provided
    if address_id is not None:
        address = await db.get(Address, address_id)
        if not address or (user is not None and address.user_id != user.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
        if lat is None and lng is None and address.latitude is not None and address.longitude is not None:
            lat = address.latitude
            lng = address.longitude
        if not pincode:
            pincode = address.pincode

    if lat is None and lng is None and not pincode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide GPS coordinates ('lat' and 'lng'), a 'pincode', or an 'address_id'",
        )

    active_stores = await list_dark_stores(db, active_only=True)
    if not active_stores:
        return ServiceabilityResponse(
            serviceable=False,
            matched_by=None,
            store=None,
            distance_km=None,
            eta_minutes=None,
            message="No active dark stores are currently available.",
            nearby_stores=[],
        )

    # 1. Primary path: GPS Haversine distance matching
    if lat is not None and lng is not None:
        ranked: list[tuple[DarkStore, float, bool, int]] = []
        for s in active_stores:
            dist = haversine_km(lat, lng, s.latitude, s.longitude)
            within = dist <= s.service_radius_km
            eta = estimate_eta_minutes(dist, s.base_prep_minutes)
            ranked.append((s, dist, within, eta))

        # Sort by distance ascending, then id ascending for determinism
        ranked.sort(key=lambda item: (item[1], item[0].id))

        nearby_list = [
            NearbyStoreInfo(
                store=DarkStoreResponse.model_validate(s),
                distance_km=round(dist, 2),
                within_service_radius=within,
                estimated_eta_minutes=eta,
            )
            for s, dist, within, eta in ranked[:5]
        ]

        serviceable_candidates = [item for item in ranked if item[2]]
        if serviceable_candidates:
            best_store, best_dist, _, best_eta = serviceable_candidates[0]
            return ServiceabilityResponse(
                serviceable=True,
                matched_by="gps_radius",
                store=DarkStoreResponse.model_validate(best_store),
                distance_km=round(best_dist, 2),
                eta_minutes=best_eta,
                message=(
                    f"Delivering in ~{best_eta} mins from {best_store.name} "
                    f"({round(best_dist, 2)} km away)."
                ),
                nearby_stores=nearby_list,
            )

        nearest_store, nearest_dist, _, _ = ranked[0]
        return ServiceabilityResponse(
            serviceable=False,
            matched_by=None,
            store=None,
            distance_km=round(nearest_dist, 2),
            eta_minutes=None,
            message=(
                f"Location is outside our delivery zone. Nearest store is {nearest_store.name} "
                f"at {round(nearest_dist, 2)} km (max radius {nearest_store.service_radius_km} km)."
            ),
            nearby_stores=nearby_list,
        )

    # 2. Fallback path: Pincode matching when GPS coordinates are not provided
    clean_pin = pincode.strip() if pincode else ""
    pin_matches = [s for s in active_stores if s.pincode == clean_pin]
    if pin_matches:
        best_store = pin_matches[0]
        # Assume ~1.5 km typical neighborhood distance when matched by pincode only
        assumed_dist = 1.5
        best_eta = estimate_eta_minutes(assumed_dist, best_store.base_prep_minutes)
        return ServiceabilityResponse(
            serviceable=True,
            matched_by="pincode_fallback",
            store=DarkStoreResponse.model_validate(best_store),
            distance_km=assumed_dist,
            eta_minutes=best_eta,
            message=f"Delivering in ~{best_eta} mins from {best_store.name} (matched by pincode {clean_pin}).",
            nearby_stores=[
                NearbyStoreInfo(
                    store=DarkStoreResponse.model_validate(s),
                    distance_km=assumed_dist,
                    within_service_radius=True,
                    estimated_eta_minutes=estimate_eta_minutes(assumed_dist, s.base_prep_minutes),
                )
                for s in pin_matches[:5]
            ],
        )

    return ServiceabilityResponse(
        serviceable=False,
        matched_by=None,
        store=None,
        distance_km=None,
        eta_minutes=None,
        message=f"Sorry, we do not currently have an active dark store servicing pincode {clean_pin}.",
        nearby_stores=[],
    )


async def resolve_store_context(
    db: AsyncSession,
    *,
    store_id: int | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> tuple[DarkStore | None, float | None, int | None]:
    """
    Helper for catalog/search/cart endpoints:
    - If `store_id` is explicitly provided, validates the store exists and is active.
      If `lat` & `lng` are also provided, computes distance and ETA to that store.
    - Otherwise, if `lat` & `lng` are provided, finds the nearest serviceable active dark store.
      Raises 404/409 if the coordinates are unserviceable.
    - If neither is provided, returns `(None, None, None)` for global catalog mode.
    """
    if (lat is None) ^ (lng is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'lat' and 'lng' must be provided together",
        )

    if store_id is not None:
        store = await get_dark_store(db, store_id, require_active=True)
        if lat is not None and lng is not None:
            dist = round(haversine_km(lat, lng, store.latitude, store.longitude), 2)
            eta = estimate_eta_minutes(dist, store.base_prep_minutes)
            return store, dist, eta
        return store, None, estimate_eta_minutes(1.2, store.base_prep_minutes)

    if lat is not None and lng is not None:
        svc = await check_serviceability(db, lat=lat, lng=lng)
        if not svc.serviceable or svc.store is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=svc.message,
            )
        store = await get_dark_store(db, svc.store.id, require_active=True)
        return store, svc.distance_km, svc.eta_minutes

    return None, None, None


async def get_store_stock_map(
    db: AsyncSession, store_id: int, item_ids: Sequence[int]
) -> dict[int, int]:
    """Return `{item_id: available_qty}` for a specific dark store (defaults to 0 if not stocked)."""
    if not item_ids:
        return {}
    rows = (
        await db.execute(
            select(DarkStoreStock.item_id, DarkStoreStock.available_qty).where(
                DarkStoreStock.store_id == store_id,
                DarkStoreStock.item_id.in_(list(item_ids)),
            )
        )
    ).all()
    stock_map = {item_id: 0 for item_id in item_ids}
    for item_id, qty in rows:
        stock_map[item_id] = int(qty)
    return stock_map


async def adjust_store_stock(
    db: AsyncSession,
    store_id: int,
    sku: str,
    delta_qty: int,
    admin_user: User,
) -> StoreItemStockResponse:
    """
    Atomically adjust stock for `sku` at `store_id` (admin restock or manual write-off).
    Locks `InventoryItem` first, then `DarkStoreStock` (same lock order as checkout) and keeps
    global `InventoryItem.available_qty` synchronized with the store-level delta.
    """
    if delta_qty == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="delta_qty cannot be zero")

    store = await get_dark_store(db, store_id)

    # Lock global InventoryItem row first
    item = (
        await db.execute(
            select(InventoryItem).where(InventoryItem.sku == sku).with_for_update()
        )
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    # Lock DarkStoreStock row if it exists
    store_stock = (
        await db.execute(
            select(DarkStoreStock)
            .where(DarkStoreStock.store_id == store.id, DarkStoreStock.item_id == item.id)
            .with_for_update()
        )
    ).scalar_one_or_none()

    current_store_qty = store_stock.available_qty if store_stock else 0
    new_store_qty = current_store_qty + delta_qty
    if new_store_qty < 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot deduct {abs(delta_qty)} units from store '{store.code}'; only {current_store_qty} available",
        )

    new_global_qty = max(0, item.available_qty + delta_qty)

    if store_stock is None:
        store_stock = DarkStoreStock(
            store_id=store.id,
            item_id=item.id,
            available_qty=new_store_qty,
        )
        db.add(store_stock)
    else:
        store_stock.available_qty = new_store_qty

    item.available_qty = new_global_qty
    await db.commit()
    await db.refresh(item)
    await db.refresh(store_stock)

    logger.info(
        f"Adjusted dark store stock for {sku} at {store.code}: {delta_qty:+d} (store={store_stock.available_qty}, global={item.available_qty})",
        extra={
            "store_id": store.id,
            "store_code": store.code,
            "sku": sku,
            "delta_qty": delta_qty,
            "store_available_qty": store_stock.available_qty,
            "global_available_qty": item.available_qty,
            "admin_id": admin_user.id,
        },
    )

    return StoreItemStockResponse(
        store_id=store.id,
        store_code=store.code,
        item_id=item.id,
        sku=item.sku,
        name=item.name,
        category=item.category,
        brand=item.brand,
        price=float(item.price),
        store_available_qty=store_stock.available_qty,
        global_available_qty=item.available_qty,
    )


async def list_store_inventory(
    db: AsyncSession,
    store_id: int,
    *,
    q: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    in_stock_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[StoreItemStockResponse]:
    """List products and their stock levels at a specific Dark Store."""
    store = await get_dark_store(db, store_id)

    store_qty_expr = func.coalesce(DarkStoreStock.available_qty, 0)
    stmt = (
        select(InventoryItem, store_qty_expr.label("store_qty"))
        .outerjoin(
            DarkStoreStock,
            and_(
                DarkStoreStock.item_id == InventoryItem.id,
                DarkStoreStock.store_id == store.id,
            ),
        )
    )

    filters = []
    if in_stock_only:
        filters.append(store_qty_expr > 0)
    if category and category.strip():
        filters.append(func.lower(InventoryItem.category) == category.strip().lower())
    if brand and brand.strip():
        filters.append(func.lower(InventoryItem.brand) == brand.strip().lower())
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                InventoryItem.name.ilike(pattern),
                InventoryItem.sku.ilike(pattern),
                InventoryItem.brand.ilike(pattern),
                InventoryItem.category.ilike(pattern),
            )
        )
    if filters:
        stmt = stmt.where(and_(*filters))

    stmt = stmt.order_by(store_qty_expr.desc(), InventoryItem.name.asc(), InventoryItem.id.asc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).all()

    return [
        StoreItemStockResponse(
            store_id=store.id,
            store_code=store.code,
            item_id=item.id,
            sku=item.sku,
            name=item.name,
            category=item.category,
            brand=item.brand,
            price=float(item.price),
            store_available_qty=int(store_qty),
            global_available_qty=item.available_qty,
        )
        for item, store_qty in rows
    ]

