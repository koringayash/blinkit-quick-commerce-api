"""Inventory & catalog endpoints: search, autocomplete, categories/brands, retrieve, create, and stock updates."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models import User
from app.schemas.item import (
    FacetCount,
    ItemCreate,
    ItemResponse,
    ItemSearchResponse,
    ItemSortBy,
    ItemUpdate,
    SearchSuggestionsResponse,
    StockUpdateRequest,
)
from app.services import item_service

router = APIRouter(prefix="/items", tags=["items"])


@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    item: ItemCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Add a new product to the inventory (admin only)."""
    return await item_service.create_inventory_item(db, item)


@router.get("", response_model=list[ItemResponse])
async def list_inventory(
    q: str | None = Query(None, max_length=100, description="Search keyword across name, SKU, brand, category, description"),
    category: list[str] | None = Query(
        None,
        description="Filter by one or more categories (e.g. ?category=Dairy&category=Bakery or ?category=Dairy,Bakery)",
    ),
    brand: list[str] | None = Query(
        None,
        description="Filter by one or more brands (e.g. ?brand=Amul&brand=Nandini or ?brand=Amul,Nandini)",
    ),
    min_price: float | None = Query(None, ge=0, description="Minimum price filter"),
    max_price: float | None = Query(None, ge=0, description="Maximum price filter"),
    in_stock: bool | None = Query(None, description="True = in-stock only, False = out-of-stock only"),
    skus: list[str] | None = Query(None, description="Retrieve a specific batch of SKUs"),
    store_id: int | None = Query(None, description="Optional Dark Store ID to show stock specific to that store"),
    lat: float | None = Query(None, ge=-90.0, le=90.0, description="Optional customer latitude to auto-select nearest dark store"),
    lng: float | None = Query(None, ge=-180.0, le=180.0, description="Optional customer longitude to auto-select nearest dark store"),
    sort_by: ItemSortBy = Query("name_asc", description="Sort order"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Browse or filter inventory items (globally or scoped to a Dark Store).
    For paginated metadata (total count, has_more, ETA, and facets), use `GET /items/search`.
    """
    res = await item_service.search_items(
        db,
        q=q,
        category=category,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        skus=skus,
        store_id=store_id,
        lat=lat,
        lng=lng,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
        include_facets=False,
    )
    return res.items


@router.get("/search", response_model=ItemSearchResponse)
async def search_inventory(
    q: str | None = Query(None, max_length=100, description="Search query (matches name, SKU, brand, category, description)"),
    category: list[str] | None = Query(
        None,
        description="Filter by one or more categories (e.g. ?category=Dairy&category=Bakery or ?category=Dairy,Bakery)",
    ),
    brand: list[str] | None = Query(
        None,
        description="Filter by one or more brands (e.g. ?brand=Amul&brand=Nandini or ?brand=Amul,Nandini)",
    ),
    min_price: float | None = Query(None, ge=0, description="Minimum price filter"),
    max_price: float | None = Query(None, ge=0, description="Maximum price filter"),
    in_stock: bool | None = Query(None, description="True = in-stock only, False = out-of-stock only"),
    skus: list[str] | None = Query(None, description="Filter to specific SKUs"),
    store_id: int | None = Query(None, description="Optional Dark Store ID to scope stock & facets"),
    lat: float | None = Query(None, ge=-90.0, le=90.0, description="Optional customer latitude to auto-select nearest dark store & compute ETA"),
    lng: float | None = Query(None, ge=-180.0, le=180.0, description="Optional customer longitude to auto-select nearest dark store & compute ETA"),
    sort_by: ItemSortBy = Query("relevance", description="Sort by relevance, price_asc, price_desc, name_asc, name_desc, or stock_desc"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Rich product search & filtering with relevance ranking, multi-category & multi-brand filters,
    dark-store / GPS serviceability scoping, pagination metadata, and dynamic filter `facets`.
    """
    return await item_service.search_items(
        db,
        q=q,
        category=category,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        skus=skus,
        store_id=store_id,
        lat=lat,
        lng=lng,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
        include_facets=True,
    )


@router.get("/suggest", response_model=SearchSuggestionsResponse)
async def autocomplete_suggestions(
    q: str = Query(..., min_length=1, max_length=100, description="Prefix or keyword for search bar autocomplete"),
    store_id: int | None = Query(None, description="Optional Dark Store ID to reflect store-specific stock"),
    limit: int = Query(8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """
    Fast typeahead / autocomplete suggestions for the search bar:
    returns matching products, categories, and brands.
    """
    return await item_service.suggest_items(db, q=q, limit=limit, store_id=store_id)


@router.get("/categories", response_model=list[FacetCount])
async def list_categories(
    brand: list[str] | None = Query(None, description="Optional filter by one or more brands"),
    store_id: int | None = Query(None, description="Optional Dark Store ID to count in-stock items at that store"),
    db: AsyncSession = Depends(get_db),
):
    """List all product categories (optionally filtered by brand and dark store) with total and in-stock item counts."""
    return await item_service.list_categories(db, brand=brand, store_id=store_id)


@router.get("/brands", response_model=list[FacetCount])
async def list_brands(
    category: list[str] | None = Query(None, description="Optional filter by one or more categories"),
    store_id: int | None = Query(None, description="Optional Dark Store ID to count in-stock items at that store"),
    db: AsyncSession = Depends(get_db),
):
    """List all product brands (optionally within one or more categories and dark store) with total and in-stock counts."""
    return await item_service.list_brands(db, category=category, store_id=store_id)


@router.get("/{sku}", response_model=ItemResponse)
async def get_item_stock(
    sku: str,
    store_id: int | None = Query(None, description="Optional Dark Store ID to view stock at that store"),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single product and its real-time stock by SKU (global or store-specific)."""
    return await item_service.get_item_for_store(db, sku, store_id=store_id)


@router.patch("/{sku}", response_model=ItemResponse)
async def update_item(
    sku: str,
    payload: ItemUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Update product details such as name, category, brand, description, or price (admin only)."""
    return await item_service.update_item_metadata(db, sku, payload)


@router.get("/{sku}/similar", response_model=list[ItemResponse])
async def get_similar_items(
    sku: str,
    store_id: int | None = Query(None, description="Optional Dark Store ID to check stock at that store"),
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve 'Frequently Bought Together' and similar items in the same category/brand.
    """
    return await item_service.get_similar_or_frequently_bought_items(
        db, sku, limit=limit, store_id=store_id
    )


@router.patch("/{sku}/stock", response_model=ItemResponse)
async def update_stock(
    sku: str,
    payload: StockUpdateRequest,
    store_id: int | None = Query(None, description="Optional Dark Store ID when purchasing from a specific store"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Negative delta = purchase (any logged-in user, recorded in order history).
    Positive delta = restock (admin only).
    """
    if payload.delta_qty == 0:
        raise HTTPException(status_code=400, detail="delta_qty cannot be zero")
    if payload.delta_qty > 0 and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can restock")
    return await item_service.apply_stock_change(
        db, sku, payload.delta_qty, user, store_id=store_id
    )
