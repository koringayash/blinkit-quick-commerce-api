"""Order business logic: atomic placement, cancellation, payment-timeout expiry and history.

Lifecycle: checkout reserves stock and creates a PENDING_PAYMENT order. Delivery is only
dispatched after payment succeeds (or COD is chosen) - see payment_service. If the order is
not paid within PAYMENT_TIMEOUT_MINUTES (or the customer cancels), the stock is released.

Lock ordering (prevents deadlocks):
1. InventoryItem rows by id ascending
2. DarkStoreStock rows by item_id ascending (when order is fulfilled by a Dark Store)
3. Order row before its Payment rows
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ORDER_EXPIRY_SWEEP_SECONDS, PAYMENT_TIMEOUT_MINUTES
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models import (
    Address,
    CartItem,
    DarkStore,
    DarkStoreStock,
    InventoryItem,
    Order,
    OrderItem,
    Payment,
    User,
)
from app.models.order import OrderStatus
from app.models.payment import PaymentStatus
from app.schemas.order import OrderLineResponse, OrderResponse
from app.services.store_service import check_serviceability, get_dark_store, haversine_km

logger = get_logger("app.orders")

MAX_CART_QTY = 50  # matches CartItemSet validation


async def _resolve_checkout_store(
    db: AsyncSession,
    user: User,
    address: Address | None,
    store_id: int | None,
) -> DarkStore | None:
    """
    Resolve which Dark Store should fulfill this checkout:
    1. If `store_id` is explicitly provided: verify the store exists and is active.
       If the customer also passed an `address` with GPS coordinates, verify the address is within
       the store's `service_radius_km`.
    2. If `store_id` is omitted and `address` is provided: if any active dark stores exist in the DB,
       find the nearest serviceable store for that address (via GPS Haversine or pincode fallback).
    """
    if store_id is not None:
        store = await get_dark_store(db, store_id, require_active=True)
        if address and address.latitude is not None and address.longitude is not None:
            dist = haversine_km(
                address.latitude, address.longitude, store.latitude, store.longitude
            )
            if dist > store.service_radius_km:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Address is {round(dist, 2)} km away from {store.name}, "
                        f"which exceeds its {store.service_radius_km} km delivery radius."
                    ),
                )
        return store

    if address is not None:
        svc = await check_serviceability(db, address_id=address.id, user=user)
        if svc.serviceable and svc.store is not None:
            return await get_dark_store(db, svc.store.id, require_active=True)
        # If active stores exist and the address has GPS coordinates that fell outside all radii,
        # block checkout with a clear unserviceable message.
        if svc.nearby_stores and address.latitude is not None and address.longitude is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=svc.message,
            )

    return None


async def place_order(
    db: AsyncSession,
    user: User,
    wanted: dict[int, int],
    address_id: int | None = None,
    store_id: int | None = None,
) -> Order:
    """
    Atomically turn {item_id: quantity} into one PENDING_PAYMENT Order.
    Locks every row (SELECT ... FOR UPDATE), checks all stock (at the target Dark Store if resolved,
    otherwise global inventory), then deducts (reserves).
    All-or-nothing: if any item is short, nothing changes. Caller must commit.
    """
    if not wanted:
        raise HTTPException(status_code=400, detail="No items to order")

    address: Address | None = None
    if address_id is not None:
        address = await db.get(Address, address_id)
        if not address or address.user_id != user.id:
            raise HTTPException(status_code=404, detail="Address not found")

    store = await _resolve_checkout_store(db, user, address, store_id)
    resolved_store_id = store.id if store else None

    # 1. Lock InventoryItem rows in a fixed order (by id ascending) so concurrent checkouts never deadlock
    result = await db.execute(
        select(InventoryItem)
        .where(InventoryItem.id.in_(wanted))
        .order_by(InventoryItem.id)
        .with_for_update()
    )
    items = result.scalars().all()

    if len(items) != len(wanted):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more items no longer exist")

    # 2. If fulfilling from a specific Dark Store, lock its DarkStoreStock rows in ascending item_id order
    store_stock_map: dict[int, DarkStoreStock] = {}
    if resolved_store_id is not None:
        ss_rows = (
            await db.execute(
                select(DarkStoreStock)
                .where(
                    DarkStoreStock.store_id == resolved_store_id,
                    DarkStoreStock.item_id.in_(wanted),
                )
                .order_by(DarkStoreStock.item_id)
                .with_for_update()
            )
        ).scalars().all()
        store_stock_map = {ss.item_id: ss for ss in ss_rows}

        shortages = []
        for i in items:
            ss = store_stock_map.get(i.id)
            avail = ss.available_qty if ss else 0
            if avail < wanted[i.id]:
                shortages.append(
                    {
                        "sku": i.sku,
                        "requested": wanted[i.id],
                        "available": avail,
                        "store_code": store.code if store else None,
                    }
                )
        if shortages:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"Insufficient stock at dark store '{store.code}'" if store else "Insufficient stock",
                    "store_id": resolved_store_id,
                    "items": shortages,
                },
            )
    else:
        shortages = [
            {"sku": i.sku, "requested": wanted[i.id], "available": i.available_qty}
            for i in items
            if i.available_qty < wanted[i.id]
        ]
        if shortages:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Insufficient stock", "items": shortages},
            )

    order = Order(
        user_id=user.id,
        address_id=address_id,
        store_id=resolved_store_id,
        status=OrderStatus.PENDING_PAYMENT,
    )
    total = Decimal("0")  # Decimal, not float: money must not accumulate rounding errors
    for i in items:
        qty = wanted[i.id]
        if resolved_store_id is not None:
            store_stock_map[i.id].available_qty -= qty
            i.available_qty = max(0, i.available_qty - qty)
        else:
            i.available_qty -= qty
        order.items.append(OrderItem(item_id=i.id, quantity=qty, unit_price=i.price))
        total += Decimal(i.price) * qty
    order.total = total.quantize(Decimal("0.01"))
    db.add(order)
    await db.flush()  # assigns order.id inside the same transaction

    logger.info(
        f"Order {order.id} created for user {user.id} ({len(items)} items, total: {order.total}, store_id={resolved_store_id})",
        extra={
            "order_id": order.id,
            "user_id": user.id,
            "store_id": resolved_store_id,
            "item_count": len(items),
            "total": order.total,
        },
    )
    return order


async def checkout_cart(
    db: AsyncSession,
    user: User,
    address_id: int | None,
    *,
    store_id: int | None = None,
) -> OrderResponse:
    cart = (await db.execute(select(CartItem).where(CartItem.user_id == user.id))).scalars().all()
    if not cart:
        raise HTTPException(status_code=400, detail="Cart is empty")

    order = await place_order(
        db,
        user,
        {c.item_id: c.quantity for c in cart},
        address_id=address_id,
        store_id=store_id,
    )
    # Same transaction: stock reserved, order created and cart cleared together, or none of it
    await db.execute(delete(CartItem).where(CartItem.user_id == user.id))
    await db.commit()
    # Delivery is NOT dispatched here: it starts once payment succeeds or COD is selected.
    return await get_order(db, user, order.id)


def _order_query(user: User, order_id: int):
    # populate_existing: refresh identity-map objects so selectin relationships (items, delivery,
    # payments, store) are actually loaded. Lazy-loading them later in async code raises MissingGreenlet.
    return (
        select(Order)
        .where(Order.id == order_id, Order.user_id == user.id)
        .execution_options(populate_existing=True)
    )


async def lock_order_for_user(db: AsyncSession, user: User, order_id: int) -> Order:
    """Load an order owned by `user` with a row lock (SELECT ... FOR UPDATE)."""
    order = (await db.execute(_order_query(user, order_id).with_for_update())).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


async def get_order(db: AsyncSession, user: User, order_id: int) -> OrderResponse:
    order = (await db.execute(_order_query(user, order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return (await _to_responses(db, [order]))[0]


async def list_orders(db: AsyncSession, user: User, limit: int, offset: int) -> list[OrderResponse]:
    result = await db.execute(
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit)
        .offset(offset)
        .execution_options(populate_existing=True)
    )
    return await _to_responses(db, result.scalars().all())


async def _release_order(db: AsyncSession, order: Order, new_status: str, reason: str) -> None:
    """
    Return the order's reserved stock to inventory (and to the fulfilling Dark Store if `store_id`
    is set) and fail any pending payment attempts.
    Caller must hold the order row lock and commit.
    """
    sorted_lines = sorted(order.items, key=lambda line: line.item_id)
    for line in sorted_lines:  # same lock order as place_order
        await db.execute(
            update(InventoryItem)
            .where(InventoryItem.id == line.item_id)
            .values(available_qty=InventoryItem.available_qty + line.quantity)
        )
        if order.store_id is not None:
            await db.execute(
                update(DarkStoreStock)
                .where(
                    DarkStoreStock.store_id == order.store_id,
                    DarkStoreStock.item_id == line.item_id,
                )
                .values(available_qty=DarkStoreStock.available_qty + line.quantity)
            )
    await db.execute(
        update(Payment)
        .where(Payment.order_id == order.id, Payment.status == PaymentStatus.PENDING)
        .values(status=PaymentStatus.FAILED, error_reason=reason)
    )
    order.status = new_status
    logger.info(
        f"Order {order.id} {new_status}: released stock for {len(order.items)} lines ({reason})",
        extra={"order_id": order.id, "store_id": order.store_id, "status": new_status, "reason": reason},
    )


async def cancel_order(db: AsyncSession, user: User, order_id: int) -> OrderResponse:
    """Cancel an unpaid order and immediately release its reserved stock."""
    order = await lock_order_for_user(db, user, order_id)
    if order.status not in OrderStatus.AWAITING_PAYMENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order is {order.status}; only unpaid orders can be cancelled",
        )
    await _release_order(db, order, OrderStatus.CANCELLED, "Order cancelled by customer")
    await db.commit()
    return await get_order(db, user, order_id)


async def expire_stale_orders(db: AsyncSession, batch_size: int = 100) -> int:
    """Release stock held by orders that were not paid within PAYMENT_TIMEOUT_MINUTES."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=PAYMENT_TIMEOUT_MINUTES)
    result = await db.execute(
        select(Order)
        .where(Order.status.in_(OrderStatus.AWAITING_PAYMENT), Order.created_at < cutoff)
        .order_by(Order.id)
        .limit(batch_size)
        # SKIP LOCKED: never block a customer paying right now, and lets several app
        # instances run the sweeper concurrently without double-releasing stock.
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    orders = result.scalars().all()
    for order in orders:
        await _release_order(db, order, OrderStatus.EXPIRED, "Payment window expired")
    await db.commit()
    return len(orders)


async def run_order_expiry_worker() -> None:
    """Background loop (started in app lifespan) that periodically expires unpaid orders."""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                expired = await expire_stale_orders(session)
            if expired:
                logger.info(f"Expired {expired} unpaid orders", extra={"expired_count": expired})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Order expiry sweep failed")
        await asyncio.sleep(ORDER_EXPIRY_SWEEP_SECONDS)


async def _to_responses(db: AsyncSession, orders: list[Order]) -> list[OrderResponse]:
    item_ids = {line.item_id for o in orders for line in o.items}
    products = {}
    if item_ids:
        rows = await db.execute(select(InventoryItem).where(InventoryItem.id.in_(item_ids)))
        products = {p.id: p for p in rows.scalars()}

    responses = []
    for o in orders:
        # Enriched delivery metadata
        delivery = o.delivery
        store = o.store

        # Enriched payment metadata: the successful attempt if any, else the latest attempt
        payment = None
        if o.payments:
            payment = next((p for p in o.payments if p.status == PaymentStatus.SUCCESS), o.payments[-1])

        responses.append(
            OrderResponse(
                id=o.id,
                status=o.status,
                address_id=o.address_id,
                store_id=o.store_id,
                store_code=store.code if store else None,
                store_name=store.name if store else None,
                total=float(o.total),
                created_at=o.created_at,
                delivery_status=delivery.status if delivery else None,
                tracking_id=delivery.tracking_id if delivery else None,
                delivery_address=delivery.delivery_address if delivery else None,
                payment_status=payment.status if payment else None,
                payment_method=payment.payment_method if payment else None,
                items=[
                    OrderLineResponse(
                        sku=products[line.item_id].sku,
                        name=products[line.item_id].name,
                        quantity=line.quantity,
                        unit_price=float(line.unit_price),
                        line_total=float(Decimal(line.unit_price) * line.quantity),
                    )
                    for line in o.items
                    if line.item_id in products
                ],
            )
        )
    return responses


async def reorder_past_order(
    db: AsyncSession, user: User, order_id: int
) -> tuple[int, list[str]]:
    """
    Transfers items from a past order back into the user's active cart.
    Skips items that are currently out of stock.
    Returns (items_added_count, out_of_stock_skus).
    """
    order = (await db.execute(_order_query(user, order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    item_ids = [line.item_id for line in order.items]
    rows = await db.execute(select(InventoryItem).where(InventoryItem.id.in_(item_ids)))
    inventory_map = {item.id: item for item in rows.scalars()}

    to_add: list[dict] = []
    out_of_stock_skus: list[str] = []
    for line in order.items:
        inv_item = inventory_map.get(line.item_id)
        qty = min(line.quantity, MAX_CART_QTY)
        if not inv_item or inv_item.available_qty < qty:
            out_of_stock_skus.append(inv_item.sku if inv_item else f"ID-{line.item_id}")
            continue
        to_add.append({"user_id": user.id, "item_id": line.item_id, "quantity": qty})

    if to_add:
        # One round-trip upsert instead of a SELECT + INSERT/UPDATE per line (also race-safe)
        stmt = pg_insert(CartItem).values(to_add)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_cart_item", set_={"quantity": stmt.excluded.quantity}
        )
        await db.execute(stmt)
    await db.commit()

    logger.info(
        f"Reordered past order {order_id} for user {user.id}: {len(to_add)} items added to cart",
        extra={"order_id": order_id, "user_id": user.id, "added": len(to_add), "out_of_stock": out_of_stock_skus},
    )
    return len(to_add), out_of_stock_skus
