"""Importing every model here registers them on Base.metadata for create_all."""
from app.models.cart import CartItem
from app.models.delivery import DeliveryAssignment
from app.models.item import InventoryItem
from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.models.store import DarkStore, DarkStoreStock
from app.models.user import Address, Favorite, User

__all__ = [
    "CartItem",
    "DarkStore",
    "DarkStoreStock",
    "DeliveryAssignment",
    "InventoryItem",
    "Order",
    "OrderItem",
    "Payment",
    "User",
    "Favorite",
    "Address",
]
