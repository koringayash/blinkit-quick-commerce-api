"""Per-user personalization endpoints: profile, favorites, orders, addresses."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Address, Favorite, InventoryItem, User
from app.schemas.order import OrderResponse, ReorderResponse
from app.schemas.user import AddressCreate, AddressResponse, FavoriteResponse, UserResponse
from app.services import order_service
from app.services.item_service import get_item_by_sku

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserResponse)
async def read_me(user: User = Depends(get_current_user)):
    return user


# --- Favorites ---
@router.get("/favorites", response_model=list[FavoriteResponse])
async def list_favorites(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(InventoryItem, Favorite.created_at)
        .join(Favorite, Favorite.item_id == InventoryItem.id)
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
    )
    return [
        FavoriteResponse(
            sku=i.sku, name=i.name, price=float(i.price), available_qty=i.available_qty, added_at=added
        )
        for i, added in result.all()
    ]


@router.put("/favorites/{sku}", status_code=status.HTTP_204_NO_CONTENT)
async def add_favorite(sku: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Idempotent: adding an existing favorite is a no-op."""
    item = await get_item_by_sku(db, sku)
    exists = await db.execute(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.item_id == item.id)
    )
    if not exists.scalar_one_or_none():
        db.add(Favorite(user_id=user.id, item_id=item.id))
        await db.commit()


@router.delete("/favorites/{sku}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(sku: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await get_item_by_sku(db, sku)
    result = await db.execute(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.item_id == item.id)
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="Item is not in favorites")
    await db.delete(fav)
    await db.commit()


# --- Orders ---
@router.get("/orders", response_model=list[OrderResponse])
async def list_orders(
    limit: int = 20, offset: int = 0,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await order_service.list_orders(db, user, min(max(limit, 1), 100), max(offset, 0))


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await order_service.get_order(db, user, order_id)


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an unpaid order and immediately release its reserved stock back to inventory."""
    return await order_service.cancel_order(db, user, order_id)


@router.post("/orders/{order_id}/reorder", response_model=ReorderResponse)
async def reorder_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    1-click Re-order: Copies in-stock items from a past order into active cart.
    Skips any items that are currently out of stock.
    """
    added_count, out_of_stock = await order_service.reorder_past_order(db, user, order_id)
    return ReorderResponse(
        order_id=order_id,
        items_added_to_cart=added_count,
        out_of_stock_skus=out_of_stock,
        message=f"Added {added_count} items to your cart."
        + (f" {len(out_of_stock)} items were out of stock." if out_of_stock else ""),
    )


# --- Addresses ---
@router.get("/addresses", response_model=list[AddressResponse])
async def list_addresses(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Address).where(Address.user_id == user.id).order_by(Address.is_default.desc(), Address.id)
    )
    return result.scalars().all()


@router.post("/addresses", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
async def add_address(
    payload: AddressCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if payload.is_default:
        # Only one default address per user
        await db.execute(update(Address).where(Address.user_id == user.id).values(is_default=False))
    address = Address(user_id=user.id, **payload.model_dump())
    db.add(address)
    await db.commit()
    await db.refresh(address)
    return address


@router.delete("/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    address = await db.get(Address, address_id)
    # Same 404 for "not found" and "not yours" so IDs of other users' addresses aren't leaked
    if not address or address.user_id != user.id:
        raise HTTPException(status_code=404, detail="Address not found")
    await db.delete(address)
    await db.commit()
