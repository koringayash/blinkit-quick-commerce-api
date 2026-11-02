"""Delivery tracking routes: REST snapshot and real-time Server-Sent Events (SSE) stream."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Order, User
from app.schemas.delivery import DeliveryStatusSnapshot
from app.services.delivery_service import (
    get_order_tracking_snapshot,
    stream_order_tracking_events,
)

router = APIRouter(prefix="/me/orders", tags=["delivery"])


async def _verify_order_ownership(order_id: int, user: User, db: AsyncSession) -> Order:
    res = await db.execute(select(Order).where(Order.id == order_id))
    order = res.scalar_one_or_none()
    if not order or order.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return order


@router.get("/{order_id}/tracking", response_model=DeliveryStatusSnapshot)
async def get_delivery_tracking(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current real-time delivery snapshot (rider details, GPS coordinates, ETA, status).
    """
    await _verify_order_ownership(order_id, user, db)
    return await get_order_tracking_snapshot(db, order_id)


@router.get("/{order_id}/tracking/stream")
async def stream_delivery_tracking(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Server-Sent Events (SSE) endpoint: streams live GPS coordinates and milestone status
    every 1 second directly to the frontend map without aggressive HTTP polling.
    """
    await _verify_order_ownership(order_id, user, db)

    return StreamingResponse(
        stream_order_tracking_events(order_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disables proxy buffering (e.g. Nginx)
        },
    )

