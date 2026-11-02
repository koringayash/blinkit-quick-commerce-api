"""Delivery partner integration and real-time tracking service.

Architecture:
- Asynchronous dispatch to third-party logistics API (without blocking checkout).
- In-memory ephemeral GPS state for 1-second real-time streaming (SSE) to prevent PostgreSQL write bloat.
- Milestone persistence: Only major lifecycle events (ASSIGNED, REACHED_DARK_STORE, PICKED_UP, OUT_FOR_DELIVERY, DELIVERED)
  are committed to PostgreSQL.
- DeliveryProvider interface with a realistic GPS movement & milestone Simulator.
"""
import asyncio
import json
import math
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.delivery import DeliveryAssignment
from app.models.order import Order
from app.schemas.delivery import DeliveryStatusSnapshot, LocationPoint, RiderInfo

logger = get_logger("app.delivery")

# Sample dark store locations for realistic quick-commerce simulations
DEFAULT_DARK_STORE_ADDRESS = "Blinkit Dark Store #14, 100ft Road, Indiranagar, Bengaluru"
DEFAULT_DARK_STORE_LAT = 12.9784
DEFAULT_DARK_STORE_LNG = 77.6408

DEFAULT_CUSTOMER_LAT = 12.9698
DEFAULT_CUSTOMER_LNG = 77.6502

SAMPLE_RIDERS = [
    {"name": "Ramesh Kumar", "phone": "+91-9876543210", "vehicle_type": "Electric Scooter (Ather 450X)"},
    {"name": "Sunil Verma", "phone": "+91-9812345678", "vehicle_type": "Motorcycle (Hero Splendor)"},
    {"name": "Amit Sharma", "phone": "+91-9988776655", "vehicle_type": "Electric Bike (Ola S1)"},
    {"name": "Deepak Patel", "phone": "+91-9723456789", "vehicle_type": "Electric Scooter (TVS iQube)"},
]


class ActiveTrackingState:
    """In-memory state for an active delivery order to stream 1-Hz GPS updates without hammering DB."""

    def __init__(
        self,
        order_id: int,
        tracking_id: str,
        partner_name: str,
        rider: dict,
        pickup_address: str,
        delivery_address: str,
        pickup_lat: float,
        pickup_lng: float,
        delivery_lat: float,
        delivery_lng: float,
    ):
        self.order_id = order_id
        self.tracking_id = tracking_id
        self.partner_name = partner_name
        self.rider = rider
        self.pickup_address = pickup_address
        self.delivery_address = delivery_address
        self.pickup_lat = pickup_lat
        self.pickup_lng = pickup_lng
        self.delivery_lat = delivery_lat
        self.delivery_lng = delivery_lng

        self.start_time = time.time()
        self.current_lat = pickup_lat + random.uniform(-0.002, 0.002)
        self.current_lng = pickup_lng + random.uniform(-0.002, 0.002)
        self.status = "ASSIGNED"
        self.last_saved_status = "ASSIGNED"

    def compute_current_snapshot(self) -> DeliveryStatusSnapshot:
        elapsed = time.time() - self.start_time

        # Milestone lifecycle timeline:
        # 0s - 10s: ASSIGNED (Rider driving to dark store)
        # 10s - 25s: REACHED_DARK_STORE (Packing & staging)
        # 25s - 40s: PICKED_UP (Picked up order, ready to move)
        # 40s - 90s: OUT_FOR_DELIVERY (Traveling to customer location)
        # 90s+: DELIVERED (Delivered)
        if elapsed < 10:
            self.status = "ASSIGNED"
            eta_minutes = 12
            # Rider slightly moving towards dark store
            t = min(1.0, elapsed / 10.0)
            self.current_lat = self.current_lat + (self.pickup_lat - self.current_lat) * t * 0.1
            self.current_lng = self.current_lng + (self.pickup_lng - self.current_lng) * t * 0.1
        elif elapsed < 25:
            self.status = "REACHED_DARK_STORE"
            self.current_lat = self.pickup_lat
            self.current_lng = self.pickup_lng
            eta_minutes = 10
        elif elapsed < 40:
            self.status = "PICKED_UP"
            self.current_lat = self.pickup_lat
            self.current_lng = self.pickup_lng
            eta_minutes = 8
        elif elapsed < 90:
            self.status = "OUT_FOR_DELIVERY"
            # Interpolate position smoothly between dark store and customer
            progress = (elapsed - 40) / 50.0  # 0.0 to 1.0
            self.current_lat = self.pickup_lat + (self.delivery_lat - self.pickup_lat) * progress
            self.current_lng = self.pickup_lng + (self.delivery_lng - self.pickup_lng) * progress
            eta_minutes = max(1, math.ceil((1.0 - progress) * 8))
        else:
            self.status = "DELIVERED"
            self.current_lat = self.delivery_lat
            self.current_lng = self.delivery_lng
            eta_minutes = 0

        return DeliveryStatusSnapshot(
            order_id=self.order_id,
            tracking_id=self.tracking_id,
            status=self.status,
            partner_name=self.partner_name,
            rider=RiderInfo(**self.rider),
            pickup_address=self.pickup_address,
            delivery_address=self.delivery_address,
            current_location=LocationPoint(
                latitude=round(self.current_lat, 6),
                longitude=round(self.current_lng, 6),
            ),
            pickup_location=LocationPoint(latitude=self.pickup_lat, longitude=self.pickup_lng),
            delivery_location=LocationPoint(latitude=self.delivery_lat, longitude=self.delivery_lng),
            eta_minutes=eta_minutes,
            last_updated_at=datetime.now(timezone.utc),
        )


class DeliveryProvider(ABC):
    """Abstract interface for third-party logistics partners (Shadowfax, Borzo, Dunzo, or Simulator)."""

    @abstractmethod
    async def request_dispatch(
        self,
        order_id: int,
        pickup_address: str,
        delivery_address: str,
        *,
        pickup_lat: float | None = None,
        pickup_lng: float | None = None,
        delivery_lat: float | None = None,
        delivery_lng: float | None = None,
    ) -> dict:
        """Call external logistics dispatch API and return assignment details."""
        pass

    @abstractmethod
    async def get_live_tracking(self, order_id: int, tracking_id: str) -> DeliveryStatusSnapshot:
        """Get current live tracking snapshot from third-party provider or in-memory state."""
        pass


class SimulatorDeliveryProvider(DeliveryProvider):
    """Realistic quick-commerce delivery simulator with live GPS coordinate calculation."""

    def __init__(self):
        self._active_trackers: dict[int, ActiveTrackingState] = {}

    async def request_dispatch(
        self,
        order_id: int,
        pickup_address: str,
        delivery_address: str,
        *,
        pickup_lat: float | None = None,
        pickup_lng: float | None = None,
        delivery_lat: float | None = None,
        delivery_lng: float | None = None,
    ) -> dict:
        # Simulate network latency of 3rd party API call
        await asyncio.sleep(0.05)

        rider = random.choice(SAMPLE_RIDERS)
        tracking_id = f"TRK-QCK-{order_id}-{random.randint(1000, 9999)}"
        partner_name = "Blinkit FastFleet"

        p_lat = pickup_lat if pickup_lat is not None else DEFAULT_DARK_STORE_LAT
        p_lng = pickup_lng if pickup_lng is not None else DEFAULT_DARK_STORE_LNG
        d_lat = delivery_lat if delivery_lat is not None else DEFAULT_CUSTOMER_LAT
        d_lng = delivery_lng if delivery_lng is not None else DEFAULT_CUSTOMER_LNG

        state = ActiveTrackingState(
            order_id=order_id,
            tracking_id=tracking_id,
            partner_name=partner_name,
            rider=rider,
            pickup_address=pickup_address or DEFAULT_DARK_STORE_ADDRESS,
            delivery_address=delivery_address or "Customer Delivery Location",
            pickup_lat=p_lat,
            pickup_lng=p_lng,
            delivery_lat=d_lat,
            delivery_lng=d_lng,
        )
        self._active_trackers[order_id] = state

        logger.info(
            f"Assigned rider {rider['name']} ({rider['vehicle_type']}) for order {order_id}",
            extra={"order_id": order_id, "tracking_id": tracking_id, "rider": rider["name"]},
        )

        return {
            "tracking_id": tracking_id,
            "partner_name": partner_name,
            "rider_name": rider["name"],
            "rider_phone": rider["phone"],
            "vehicle_type": rider["vehicle_type"],
            "status": "ASSIGNED",
            "pickup_address": state.pickup_address,
            "delivery_address": state.delivery_address,
        }

    async def get_live_tracking(self, order_id: int, tracking_id: str) -> DeliveryStatusSnapshot:
        state = self._active_trackers.get(order_id)
        if not state:
            # If not in active memory, construct from basic defaults or completed state
            return DeliveryStatusSnapshot(
                order_id=order_id,
                tracking_id=tracking_id,
                status="DELIVERED",
                partner_name="Blinkit FastFleet",
                rider=RiderInfo(name="Ramesh Kumar", phone="+91-9876543210", vehicle_type="Electric Scooter"),
                pickup_address=DEFAULT_DARK_STORE_ADDRESS,
                delivery_address="Customer Location",
                current_location=LocationPoint(latitude=DEFAULT_CUSTOMER_LAT, longitude=DEFAULT_CUSTOMER_LNG),
                pickup_location=LocationPoint(latitude=DEFAULT_DARK_STORE_LAT, longitude=DEFAULT_DARK_STORE_LNG),
                delivery_location=LocationPoint(latitude=DEFAULT_CUSTOMER_LAT, longitude=DEFAULT_CUSTOMER_LNG),
                eta_minutes=0,
                last_updated_at=datetime.now(timezone.utc),
            )

        snapshot = state.compute_current_snapshot()

        # Check if milestone status changed, and if so, sync to DB asynchronously
        if state.status != state.last_saved_status:
            state.last_saved_status = state.status
            asyncio.create_task(self._sync_milestone_to_db(order_id, state.status))

        return snapshot

    async def _sync_milestone_to_db(self, order_id: int, new_status: str) -> None:
        """Asynchronously syncs milestone transitions to DB."""
        try:
            async with AsyncSessionLocal() as session:
                # Update DeliveryAssignment
                res = await session.execute(
                    select(DeliveryAssignment).where(DeliveryAssignment.order_id == order_id)
                )
                assignment = res.scalar_one_or_none()
                if assignment:
                    assignment.status = new_status
                    if new_status == "DELIVERED":
                        assignment.delivered_at = datetime.now(timezone.utc)

                # Update Order status
                order_res = await session.execute(select(Order).where(Order.id == order_id))
                order = order_res.scalar_one_or_none()
                if order:
                    order.status = new_status

                await session.commit()
                logger.info(
                    f"Synced milestone status '{new_status}' for order {order_id} to DB",
                    extra={"order_id": order_id, "status": new_status},
                )
        except Exception as e:
            logger.error(f"Error syncing milestone to DB for order {order_id}: {e}")

    def get_state(self, order_id: int) -> ActiveTrackingState | None:
        return self._active_trackers.get(order_id)


# Global provider instance (defaults to our high-fidelity simulator)
delivery_provider: DeliveryProvider = SimulatorDeliveryProvider()


async def dispatch_order_delivery(
    order_id: int,
    delivery_address: str | None = None,
    *,
    pickup_address: str | None = None,
    pickup_lat: float | None = None,
    pickup_lng: float | None = None,
    delivery_lat: float | None = None,
    delivery_lng: float | None = None,
) -> None:
    """
    Background task to dispatch order to third-party delivery partner and persist assignment.
    Runs asynchronously without delaying customer checkout response.
    """
    try:
        data = await delivery_provider.request_dispatch(
            order_id=order_id,
            pickup_address=pickup_address or DEFAULT_DARK_STORE_ADDRESS,
            delivery_address=delivery_address or "Customer Delivery Address",
            pickup_lat=pickup_lat,
            pickup_lng=pickup_lng,
            delivery_lat=delivery_lat,
            delivery_lng=delivery_lng,
        )

        async with AsyncSessionLocal() as session:
            # Check if assignment already exists
            existing = await session.execute(
                select(DeliveryAssignment).where(DeliveryAssignment.order_id == order_id)
            )
            if existing.scalar_one_or_none():
                return

            assignment = DeliveryAssignment(
                order_id=order_id,
                tracking_id=data["tracking_id"],
                partner_name=data["partner_name"],
                rider_name=data["rider_name"],
                rider_phone=data["rider_phone"],
                vehicle_type=data["vehicle_type"],
                status=data["status"],
                pickup_address=data["pickup_address"],
                delivery_address=data["delivery_address"],
            )
            session.add(assignment)
            await session.commit()
            logger.info(
                f"Persisted delivery assignment {data['tracking_id']} for order {order_id}",
                extra={"order_id": order_id, "tracking_id": data["tracking_id"]},
            )
    except Exception as e:
        logger.error(f"Failed to dispatch delivery for order {order_id}: {e}", exc_info=True)


async def get_order_tracking_snapshot(db: AsyncSession, order_id: int) -> DeliveryStatusSnapshot:
    """Fetch current delivery tracking snapshot for a given order."""
    res = await db.execute(select(DeliveryAssignment).where(DeliveryAssignment.order_id == order_id))
    assignment = res.scalar_one_or_none()
    tracking_id = assignment.tracking_id if assignment else f"TRK-{order_id}"
    return await delivery_provider.get_live_tracking(order_id, tracking_id)


async def stream_order_tracking_events(order_id: int) -> AsyncGenerator[str, None]:
    """
    Generates Server-Sent Events (SSE) every 1 second pushing live GPS & status.
    Format: 'event: tracking\ndata: {json}\n\n'
    """
    try:
        while True:
            tracking_id = f"TRK-{order_id}"
            snapshot = await delivery_provider.get_live_tracking(order_id, tracking_id)
            payload = snapshot.model_dump_json()

            yield f"event: tracking\ndata: {payload}\n\n"

            if snapshot.status == "DELIVERED":
                # Push delivered event and close stream cleanly
                yield "event: complete\ndata: {\"message\": \"Order delivered successfully\"}\n\n"
                break

            await asyncio.sleep(1.0)
    except (asyncio.CancelledError, GeneratorExit):
        logger.info(f"Tracking stream closed for order {order_id}")
        return