"""Inventory, product search, autocomplete, and recommendation business logic (global & dark-store scoped)."""
from collections.abc import Sequence

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.logging import get_logger
from app.models import DarkStoreStock, InventoryItem, OrderItem, User
from app.schemas.item import (
    FacetCount,
    ItemCreate,
    ItemResponse,
    ItemSearchResponse,
    ItemSortBy,
    ItemUpdate,
    ProductSuggestion,
    SearchFacets,
    SearchSuggestionsResponse,
)
from app.services.order_service import place_order
from app.services.store_service import get_store_stock_map, resolve_store_context

logger = get_logger("app.inventory")

MAX_SEARCH_TOKENS = 6


def _escape_like(term: str) -> str:
    """Escape SQL LIKE/ILIKE wildcard characters so user input is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _normalize_multi_values(raw: str | Sequence[str] | None) -> list[str]:
    """
    Accepts a single string, comma-separated string ('Amul,Nandini'), or repeated query params
    (['Amul', 'Nandini']) and returns normalized lowercase distinct values.
    """
    if not raw:
        return []
    items = [raw] if isinstance(raw, str) else list(raw)
    normalized: list[str] = []
    for entry in items:
        for part in entry.split(","):
            clean = part.strip().lower()
            if clean and clean not in normalized:
                normalized.append(clean)
    return normalized


def _stock_expr(store_id: int | None):
    """Return the SQL expression representing available stock (per-store if store_id is set, else global)."""
    if store_id is not None:
        return func.coalesce(DarkStoreStock.available_qty, 0)
    return InventoryItem.available_qty


def _apply_store_outerjoin(stmt, store_id: int | None):
    """If `store_id` is set, outer-join `DarkStoreStock` for that store."""
    if store_id is not None:
        return stmt.outerjoin(
            DarkStoreStock,
            and_(
                DarkStoreStock.item_id == InventoryItem.id,
                DarkStoreStock.store_id == store_id,
            ),
        )
    return stmt


def _to_item_response(item: InventoryItem, available_qty: int | None = None) -> ItemResponse:
    qty = item.available_qty if available_qty is None else int(available_qty)
    return ItemResponse(
        id=item.id,
        sku=item.sku,
        name=item.name,
        category=item.category,
        brand=item.brand,
        description=item.description,
        price=float(item.price),
        available_qty=qty,
    )


async def get_item_by_sku(db: AsyncSession, sku: str, *, lock: bool = False) -> InventoryItem:
    stmt = select(InventoryItem).where(InventoryItem.sku == sku)
    if lock:
        # Row-level lock on this SKU until the transaction commits
        stmt = stmt.with_for_update()
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


async def get_item_for_store(
    db: AsyncSession, sku: str, *, store_id: int | None = None
) -> ItemResponse:
    """Retrieve a single SKU, optionally with stock scoped to a specific Dark Store."""
    item = await get_item_by_sku(db, sku)
    if store_id is None:
        return _to_item_response(item)
    await resolve_store_context(db, store_id=store_id)
    stock_map = await get_store_stock_map(db, store_id, [item.id])
    return _to_item_response(item, stock_map.get(item.id, 0))


async def create_inventory_item(db: AsyncSession, payload: ItemCreate) -> InventoryItem:
    """Create a new product atomically (race-safe on duplicate SKU)."""
    stmt = (
        pg_insert(InventoryItem)
        .values(**payload.model_dump())
        .on_conflict_do_nothing(index_elements=[InventoryItem.sku])
        .returning(InventoryItem)
    )
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SKU already exists")
    await db.commit()
    logger.info(
        f"Created item {item.sku} ({item.name}, price={item.price}, qty={item.available_qty})",
        extra={"sku": item.sku, "category": item.category, "brand": item.brand},
    )
    return item


async def update_item_metadata(
    db: AsyncSession, sku: str, payload: ItemUpdate
) -> InventoryItem:
    """Update product details (name, category, brand, description, price)."""
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided for update",
        )
    item = await get_item_by_sku(db, sku, lock=True)
    for field, value in updates.items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    logger.info(f"Updated metadata for SKU {sku}", extra={"sku": sku, "updated_fields": list(updates.keys())})
    return item


def _build_search_filters(
    *,
    q: str | None = None,
    category: str | Sequence[str] | None = None,
    brand: str | Sequence[str] | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    in_stock: bool | None = None,
    skus: Sequence[str] | None = None,
    store_id: int | None = None,
) -> list:
    filters = []
    stock_col = _stock_expr(store_id)

    if skus:
        filters.append(InventoryItem.sku.in_(list(skus)))

    categories = _normalize_multi_values(category)
    if len(categories) == 1:
        filters.append(func.lower(InventoryItem.category) == categories[0])
    elif len(categories) > 1:
        filters.append(func.lower(InventoryItem.category).in_(categories))

    brands = _normalize_multi_values(brand)
    if len(brands) == 1:
        filters.append(func.lower(InventoryItem.brand) == brands[0])
    elif len(brands) > 1:
        filters.append(func.lower(InventoryItem.brand).in_(brands))

    if min_price is not None:
        filters.append(InventoryItem.price >= min_price)

    if max_price is not None:
        filters.append(InventoryItem.price <= max_price)

    if in_stock is True:
        filters.append(stock_col > 0)
    elif in_stock is False:
        filters.append(stock_col == 0)

    if q and q.strip():
        tokens = [t for t in q.strip().split() if t][:MAX_SEARCH_TOKENS]
        for token in tokens:
            pattern = f"%{_escape_like(token)}%"
            filters.append(
                or_(
                    InventoryItem.name.ilike(pattern, escape="\\"),
                    InventoryItem.sku.ilike(pattern, escape="\\"),
                    InventoryItem.category.ilike(pattern, escape="\\"),
                    InventoryItem.brand.ilike(pattern, escape="\\"),
                    InventoryItem.description.ilike(pattern, escape="\\"),
                )
            )

    return filters


def _build_order_by(q: str | None, sort_by: ItemSortBy, store_id: int | None = None) -> list:
    stock_col = _stock_expr(store_id)
    in_stock_priority = case((stock_col > 0, 1), else_=0).desc()

    if sort_by == "name_asc":
        return [InventoryItem.name.asc(), InventoryItem.id.asc()]
    if sort_by == "name_desc":
        return [InventoryItem.name.desc(), InventoryItem.id.asc()]
    if sort_by == "price_asc":
        return [InventoryItem.price.asc(), InventoryItem.name.asc(), InventoryItem.id.asc()]
    if sort_by == "price_desc":
        return [InventoryItem.price.desc(), InventoryItem.name.asc(), InventoryItem.id.asc()]
    if sort_by == "stock_desc":
        return [stock_col.desc(), InventoryItem.name.asc(), InventoryItem.id.asc()]

    # "relevance" sort
    if q and q.strip():
        clean_q = q.strip()
        lower_q = clean_q.lower()
        escaped = _escape_like(clean_q)
        prefix_pat = f"{escaped}%"
        substr_pat = f"%{escaped}%"

        relevance_score = (
            case((func.lower(InventoryItem.sku) == lower_q, 100), else_=0)
            + case((func.lower(InventoryItem.name) == lower_q, 90), else_=0)
            + case((InventoryItem.name.ilike(prefix_pat, escape="\\"), 60), else_=0)
            + case((InventoryItem.brand.ilike(prefix_pat, escape="\\"), 45), else_=0)
            + case((InventoryItem.sku.ilike(prefix_pat, escape="\\"), 40), else_=0)
            + case((InventoryItem.name.ilike(substr_pat, escape="\\"), 30), else_=0)
            + case((InventoryItem.category.ilike(substr_pat, escape="\\"), 20), else_=0)
            + case((stock_col > 0, 15), else_=0)
        )
        return [relevance_score.desc(), in_stock_priority, InventoryItem.name.asc(), InventoryItem.id.asc()]

    return [in_stock_priority, InventoryItem.name.asc(), InventoryItem.id.asc()]


async def _compute_search_facets(
    db: AsyncSession, filters: list, store_id: int | None = None
) -> SearchFacets:
    """Compute category counts, brand counts, and price range for the active search/filter set."""
    stock_col = _stock_expr(store_id)

    cat_stmt = _apply_store_outerjoin(
        select(
            InventoryItem.category.label("name"),
            func.count(InventoryItem.id).label("total_items"),
            func.coalesce(func.sum(case((stock_col > 0, 1), else_=0)), 0).label("in_stock_items"),
        ),
        store_id,
    ).where(InventoryItem.category.is_not(None), *filters).group_by(
        InventoryItem.category
    ).order_by(func.count(InventoryItem.id).desc(), InventoryItem.category.asc())

    brand_stmt = _apply_store_outerjoin(
        select(
            InventoryItem.brand.label("name"),
            func.count(InventoryItem.id).label("total_items"),
            func.coalesce(func.sum(case((stock_col > 0, 1), else_=0)), 0).label("in_stock_items"),
        ),
        store_id,
    ).where(InventoryItem.brand.is_not(None), *filters).group_by(
        InventoryItem.brand
    ).order_by(func.count(InventoryItem.id).desc(), InventoryItem.brand.asc())

    price_stmt = _apply_store_outerjoin(
        select(
            func.min(InventoryItem.price).label("min_price"),
            func.max(InventoryItem.price).label("max_price"),
        ),
        store_id,
    )
    if filters:
        price_stmt = price_stmt.where(and_(*filters))

    cat_rows = (await db.execute(cat_stmt)).all()
    brand_rows = (await db.execute(brand_stmt)).all()
    price_row = (await db.execute(price_stmt)).one()

    return SearchFacets(
        categories=[
            FacetCount(name=r.name, total_items=int(r.total_items), in_stock_items=int(r.in_stock_items))
            for r in cat_rows
        ],
        brands=[
            FacetCount(name=r.name, total_items=int(r.total_items), in_stock_items=int(r.in_stock_items))
            for r in brand_rows
        ],
        min_price=float(price_row.min_price) if price_row.min_price is not None else None,
        max_price=float(price_row.max_price) if price_row.max_price is not None else None,
    )


async def search_items(
    db: AsyncSession,
    *,
    q: str | None = None,
    category: str | Sequence[str] | None = None,
    brand: str | Sequence[str] | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    in_stock: bool | None = None,
    skus: Sequence[str] | None = None,
    store_id: int | None = None,
    lat: float | None = None,
    lng: float | None = None,
    sort_by: ItemSortBy = "relevance",
    limit: int = 20,
    offset: int = 0,
    include_facets: bool = True,
) -> ItemSearchResponse:
    """
    Full search and filter query returning paginated items, total count, and available facets.
    Supports filtering by one or multiple categories and brands simultaneously, and optional
    scoping to a specific Dark Store (`store_id`) or customer GPS coordinates (`lat`, `lng`).
    """
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_price cannot be greater than max_price",
        )

    store, distance_km, eta_minutes = await resolve_store_context(
        db, store_id=store_id, lat=lat, lng=lng
    )
    resolved_store_id = store.id if store else None

    filters = _build_search_filters(
        q=q,
        category=category,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        skus=skus,
        store_id=resolved_store_id,
    )

    count_stmt = _apply_store_outerjoin(select(func.count(InventoryItem.id)), resolved_store_id)
    if filters:
        count_stmt = count_stmt.where(and_(*filters))
    total = (await db.execute(count_stmt)).scalar_one()

    stock_col = _stock_expr(resolved_store_id)
    stmt = _apply_store_outerjoin(
        select(InventoryItem, stock_col.label("effective_qty")), resolved_store_id
    )
    if filters:
        stmt = stmt.where(and_(*filters))
    stmt = (
        stmt.order_by(*_build_order_by(q, sort_by, resolved_store_id))
        .limit(limit)
        .offset(offset)
    )

    rows = (await db.execute(stmt)).all()
    items = [_to_item_response(item, eff_qty) for item, eff_qty in rows]
    facets = (
        await _compute_search_facets(db, filters, resolved_store_id)
        if include_facets
        else SearchFacets()
    )

    return ItemSearchResponse(
        store_id=store.id if store else None,
        store_code=store.code if store else None,
        eta_minutes=eta_minutes,
        distance_km=distance_km,
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(items)) < total,
        facets=facets,
    )


async def suggest_items(
    db: AsyncSession, q: str, limit: int = 8, *, store_id: int | None = None
) -> SearchSuggestionsResponse:
    """
    Fast typeahead / autocomplete suggestions for the search bar:
    returns top matching products, categories, and brands (optionally scoped to a dark store).
    """
    clean_q = q.strip()
    if not clean_q:
        return SearchSuggestionsResponse(
            query="", products=[], matching_categories=[], matching_brands=[]
        )

    if store_id is not None:
        await resolve_store_context(db, store_id=store_id)

    escaped = _escape_like(clean_q)
    substr_pat = f"%{escaped}%"
    prefix_pat = f"{escaped}%"
    stock_col = _stock_expr(store_id)

    # 1. Top product suggestions (prioritize prefix match & in-stock)
    score = (
        case((InventoryItem.name.ilike(prefix_pat, escape="\\"), 50), else_=0)
        + case((InventoryItem.brand.ilike(prefix_pat, escape="\\"), 30), else_=0)
        + case((InventoryItem.sku.ilike(prefix_pat, escape="\\"), 25), else_=0)
        + case((stock_col > 0, 15), else_=0)
    )
    prod_stmt = (
        _apply_store_outerjoin(
            select(InventoryItem, stock_col.label("effective_qty")), store_id
        )
        .where(
            or_(
                InventoryItem.name.ilike(substr_pat, escape="\\"),
                InventoryItem.brand.ilike(substr_pat, escape="\\"),
                InventoryItem.category.ilike(substr_pat, escape="\\"),
                InventoryItem.sku.ilike(substr_pat, escape="\\"),
            )
        )
        .order_by(score.desc(), InventoryItem.name.asc())
        .limit(limit)
    )
    products = (await db.execute(prod_stmt)).all()

    # 2. Matching distinct categories
    cat_stmt = (
        select(InventoryItem.category)
        .where(
            InventoryItem.category.is_not(None),
            InventoryItem.category.ilike(substr_pat, escape="\\"),
        )
        .distinct()
        .order_by(InventoryItem.category.asc())
        .limit(5)
    )
    categories = [c for c in (await db.execute(cat_stmt)).scalars().all() if c]

    # 3. Matching distinct brands
    brand_stmt = (
        select(InventoryItem.brand)
        .where(
            InventoryItem.brand.is_not(None),
            InventoryItem.brand.ilike(substr_pat, escape="\\"),
        )
        .distinct()
        .order_by(InventoryItem.brand.asc())
        .limit(5)
    )
    brands = [b for b in (await db.execute(brand_stmt)).scalars().all() if b]

    return SearchSuggestionsResponse(
        query=clean_q,
        products=[
            ProductSuggestion(
                sku=p.sku,
                name=p.name,
                category=p.category,
                brand=p.brand,
                price=float(p.price),
                in_stock=int(eff_qty) > 0,
            )
            for p, eff_qty in products
        ],
        matching_categories=categories,
        matching_brands=brands,
    )


async def list_categories(
    db: AsyncSession,
    brand: str | Sequence[str] | None = None,
    *,
    store_id: int | None = None,
) -> list[FacetCount]:
    """Return all product categories (optionally filtered by brand and/or dark store) with counts."""
    if store_id is not None:
        await resolve_store_context(db, store_id=store_id)

    filters = [InventoryItem.category.is_not(None)]
    brands = _normalize_multi_values(brand)
    if len(brands) == 1:
        filters.append(func.lower(InventoryItem.brand) == brands[0])
    elif len(brands) > 1:
        filters.append(func.lower(InventoryItem.brand).in_(brands))

    stock_col = _stock_expr(store_id)
    stmt = (
        _apply_store_outerjoin(
            select(
                InventoryItem.category.label("name"),
                func.count(InventoryItem.id).label("total_items"),
                func.coalesce(
                    func.sum(case((stock_col > 0, 1), else_=0)), 0
                ).label("in_stock_items"),
            ),
            store_id,
        )
        .where(and_(*filters))
        .group_by(InventoryItem.category)
        .order_by(func.count(InventoryItem.id).desc(), InventoryItem.category.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        FacetCount(
            name=row.name,
            total_items=int(row.total_items),
            in_stock_items=int(row.in_stock_items),
        )
        for row in rows
    ]


async def list_brands(
    db: AsyncSession,
    category: str | Sequence[str] | None = None,
    *,
    store_id: int | None = None,
) -> list[FacetCount]:
    """Return all product brands (optionally filtered by category and/or dark store) with counts."""
    if store_id is not None:
        await resolve_store_context(db, store_id=store_id)

    filters = [InventoryItem.brand.is_not(None)]
    categories = _normalize_multi_values(category)
    if len(categories) == 1:
        filters.append(func.lower(InventoryItem.category) == categories[0])
    elif len(categories) > 1:
        filters.append(func.lower(InventoryItem.category).in_(categories))

    stock_col = _stock_expr(store_id)
    stmt = (
        _apply_store_outerjoin(
            select(
                InventoryItem.brand.label("name"),
                func.count(InventoryItem.id).label("total_items"),
                func.coalesce(
                    func.sum(case((stock_col > 0, 1), else_=0)), 0
                ).label("in_stock_items"),
            ),
            store_id,
        )
        .where(and_(*filters))
        .group_by(InventoryItem.brand)
        .order_by(func.count(InventoryItem.id).desc(), InventoryItem.brand.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        FacetCount(
            name=row.name,
            total_items=int(row.total_items),
            in_stock_items=int(row.in_stock_items),
        )
        for row in rows
    ]


async def get_similar_or_frequently_bought_items(
    db: AsyncSession, sku: str, limit: int = 6, *, store_id: int | None = None
) -> list[ItemResponse]:
    """
    Recommend related products for a given SKU:
    1. First ranks items frequently bought in the same order (co-occurrence in order_items).
    2. Fills remaining slots with items in the same category or brand.
    If `store_id` is provided, stock availability reflects that Dark Store.
    """
    if store_id is not None:
        await resolve_store_context(db, store_id=store_id)

    target = await get_item_by_sku(db, sku)
    collected: list[InventoryItem] = []
    seen_ids: set[int] = {target.id}

    # 1. Co-purchased items from order_items
    oi_source = aliased(OrderItem)
    oi_other = aliased(OrderItem)
    copurchase_stmt = (
        select(InventoryItem)
        .join(oi_other, oi_other.item_id == InventoryItem.id)
        .join(oi_source, oi_source.order_id == oi_other.order_id)
        .where(
            oi_source.item_id == target.id,
            oi_other.item_id != target.id,
        )
        .group_by(InventoryItem.id)
        .order_by(
            case((InventoryItem.available_qty > 0, 1), else_=0).desc(),
            func.count(oi_other.id).desc(),
            InventoryItem.name.asc(),
        )
        .limit(limit)
    )
    copurchased = (await db.execute(copurchase_stmt)).scalars().all()
    for item in copurchased:
        collected.append(item)
        seen_ids.add(item.id)

    # 2. Fallback to same category / brand if needed
    remaining = limit - len(collected)
    if remaining > 0 and (target.category or target.brand):
        similarity_clauses = []
        if target.category:
            similarity_clauses.append(func.lower(InventoryItem.category) == target.category.lower())
        if target.brand:
            similarity_clauses.append(func.lower(InventoryItem.brand) == target.brand.lower())

        sim_score = (
            (
                case(
                    (func.lower(InventoryItem.category) == target.category.lower(), 20),
                    else_=0,
                )
                if target.category
                else 0
            )
            + (
                case(
                    (func.lower(InventoryItem.brand) == target.brand.lower(), 10),
                    else_=0,
                )
                if target.brand
                else 0
            )
            + case((InventoryItem.available_qty > 0, 15), else_=0)
        )

        fallback_stmt = (
            select(InventoryItem)
            .where(
                InventoryItem.id.not_in(seen_ids),
                or_(*similarity_clauses),
            )
            .order_by(sim_score.desc(), InventoryItem.name.asc())
            .limit(remaining)
        )
        fallbacks = (await db.execute(fallback_stmt)).scalars().all()
        collected.extend(fallbacks)

    if store_id is None:
        return [_to_item_response(item) for item in collected]

    stock_map = await get_store_stock_map(db, store_id, [item.id for item in collected])
    return [_to_item_response(item, stock_map.get(item.id, 0)) for item in collected]


async def apply_stock_change(
    db: AsyncSession,
    sku: str,
    delta_qty: int,
    user: User,
    *,
    store_id: int | None = None,
) -> InventoryItem:
    """
    Atomically update stock when a user buys an item or an admin restocks.
    Uses SELECT ... FOR UPDATE (Pessimistic Locking) to prevent race conditions.
    Negative delta = purchase (recorded in order history). Positive delta = restock.
    """
    if delta_qty < 0:
        # Purchase ("Buy now"): same locked, all-or-nothing path as cart checkout.
        # Creates a PENDING_PAYMENT order; delivery is dispatched once it is paid (see payment_service).
        item = await get_item_by_sku(db, sku)
        await place_order(db, user, {item.id: -delta_qty}, store_id=store_id)
        await db.commit()
        await db.refresh(item)
        return item

    # Restock: lock the row, add stock, commit (releases the lock)
    item = await get_item_by_sku(db, sku, lock=True)
    item.available_qty += delta_qty
    await db.commit()
    await db.refresh(item)
    logger.info(
        f"Restocked {sku}: +{delta_qty} units (now {item.available_qty})",
        extra={"sku": sku, "delta_qty": delta_qty, "new_stock": item.available_qty, "admin_id": user.id},
    )
    return item
