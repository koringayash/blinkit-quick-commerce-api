"""Shopping cart. Adding to cart does NOT touch stock; stock is deducted at checkout."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CartItem, InventoryItem, User
from app.schemas.cart import CartItemSet, CartLine, CartResponse, CheckoutRequest
from app.schemas.order import OrderResponse
from app.services import order_service
from app.services.item_service import get_item_by_sku
from app.services.store_service import get_dark_store, get_store_stock_map

router = APIRouter(prefix="/me/cart", tags=["cart"])


@router.get("", response_model=CartResponse)
async def view_cart(
    store_id: int | None = Query(
        None,
        description="Optional Dark Store ID to check item availability at a specific neighborhood store",
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cart with live prices and a stock warning per line (globally or at a specific dark store)."""
    store = await get_dark_store(db, store_id, require_active=True) if store_id is not None else None

    result = await db.execute(
        select(CartItem, InventoryItem)
        .join(InventoryItem, InventoryItem.id == CartItem.item_id)
        .where(CartItem.user_id == user.id)
        .order_by(CartItem.added_at)
    )
    rows = result.all()

    stock_map: dict[int, int] = {}
    if store is not None and rows:
        stock_map = await get_store_stock_map(db, store.id, [i.id for _, i in rows])

    lines = []
    for c, i in rows:
        avail = stock_map.get(i.id, 0) if store is not None else i.available_qty
        lines.append(
            CartLine(
                sku=i.sku,
                name=i.name,
                unit_price=float(i.price),
                quantity=c.quantity,
                line_total=round(float(i.price) * c.quantity, 2),
                available_qty=avail,
                in_stock=avail >= c.quantity,
                added_at=c.added_at,
            )
        )
    return CartResponse(
        store_id=store.id if store else None,
        store_code=store.code if store else None,
        items=lines,
        item_count=sum(l.quantity for l in lines),
        subtotal=round(sum(l.line_total for l in lines), 2),
    )


@router.put("/{sku}", status_code=status.HTTP_204_NO_CONTENT)
async def set_cart_item(
    sku: str,
    payload: CartItemSet,
    store_id: int | None = Query(
        None,
        description="Optional Dark Store ID to verify stock against that specific store",
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set the quantity of an item (adds it if missing). Idempotent."""
    item = await get_item_by_sku(db, sku)
    if store_id is not None:
        store = await get_dark_store(db, store_id, require_active=True)
        stock_map = await get_store_stock_map(db, store.id, [item.id])
        avail = stock_map.get(item.id, 0)
    else:
        avail = item.available_qty

    if payload.quantity > avail:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only {avail} units available",
        )
    result = await db.execute(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.item_id == item.id)
    )
    line = result.scalar_one_or_none()
    if line:
        line.quantity = payload.quantity
    else:
        db.add(CartItem(user_id=user.id, item_id=item.id, quantity=payload.quantity))
    await db.commit()


@router.delete("/{sku}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_cart_item(sku: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await get_item_by_sku(db, sku)
    result = await db.execute(
        delete(CartItem).where(CartItem.user_id == user.id, CartItem.item_id == item.id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Item is not in cart")
    await db.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(CartItem).where(CartItem.user_id == user.id))
    await db.commit()


@router.post("/checkout", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def checkout(
    payload: CheckoutRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lock stock, deduct, create one order with all cart lines, empty the cart. All-or-nothing."""
    address_id = payload.address_id if payload else None
    store_id = payload.store_id if payload else None
    return await order_service.checkout_cart(db, user, address_id, store_id=store_id)
