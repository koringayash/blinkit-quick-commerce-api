"""Idempotent initial database seeder for Dark Stores, Catalog Products, Per-Store Stock, and Demo Users."""
from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.security import hash_password_async
from app.models import Address, DarkStore, DarkStoreStock, InventoryItem, User

logger = get_logger("app.seed")

INITIAL_STORES = [
    {
        "code": "BLR-IND-01",
        "name": "QuickKart Dark Store - Indiranagar 100ft Rd",
        "address": "100ft Road, HAL 2nd Stage, Indiranagar",
        "city": "Bengaluru",
        "pincode": "560038",
        "latitude": 12.9784,
        "longitude": 77.6408,
        "service_radius_km": 3.5,
        "base_prep_minutes": 3,
        "is_active": True,
    },
    {
        "code": "BLR-KOR-01",
        "name": "QuickKart Dark Store - Koramangala 5th Block",
        "address": "80ft Road, 5th Block, Koramangala",
        "city": "Bengaluru",
        "pincode": "560034",
        "latitude": 12.9352,
        "longitude": 77.6245,
        "service_radius_km": 3.5,
        "base_prep_minutes": 3,
        "is_active": True,
    },
    {
        "code": "BOM-BND-01",
        "name": "QuickKart Dark Store - Bandra West Linking Rd",
        "address": "Linking Road, Bandra West",
        "city": "Mumbai",
        "pincode": "400050",
        "latitude": 19.0596,
        "longitude": 72.8295,
        "service_radius_km": 3.0,
        "base_prep_minutes": 4,
        "is_active": True,
    },
    {
        "code": "AMD-NAV-01",
        "name": "QuickKart Dark Store - Navrangpura CG Rd",
        "address": "CG Road, Navrangpura",
        "city": "Ahmedabad",
        "pincode": "380009",
        "latitude": 23.0365,
        "longitude": 72.5611,
        "service_radius_km": 4.0,
        "base_prep_minutes": 3,
        "is_active": True,
    },
]

INITIAL_PRODUCTS = [
    {
        "sku": "MILK-NANDINI-500ML",
        "name": "Nandini GoodLife Toned Milk 500ml",
        "category": "Dairy & Breakfast",
        "brand": "Nandini",
        "description": "Fresh pasteurized toned milk, rich in calcium and protein.",
        "price": 27.0,
        "store_qtys": [40, 35, 20, 25],
    },
    {
        "sku": "MILK-AMUL-TAZA-1L",
        "name": "Amul Taaza Homogenised Toned Milk 1L",
        "category": "Dairy & Breakfast",
        "brand": "Amul",
        "description": "UHT treated long-life toned milk, no boiling required.",
        "price": 72.0,
        "store_qtys": [30, 25, 40, 35],
    },
    {
        "sku": "BUTTER-AMUL-100G",
        "name": "Amul Pasteurised Butter 100g",
        "category": "Dairy & Breakfast",
        "brand": "Amul",
        "description": "Utterly butterly delicious salted table butter.",
        "price": 58.0,
        "store_qtys": [25, 30, 30, 25],
    },
    {
        "sku": "CURD-MOTHERDAIRY-400G",
        "name": "Mother Dairy Classic Pouch Curd 400g",
        "category": "Dairy & Breakfast",
        "brand": "Mother Dairy",
        "description": "Thick, creamy and delicious dahi made from pasteurized milk.",
        "price": 35.0,
        "store_qtys": [20, 18, 22, 15],
    },
    {
        "sku": "BREAD-BRITANNIA-WW-400G",
        "name": "Britannia 100% Whole Wheat Bread 400g",
        "category": "Bakery & Biscuits",
        "brand": "Britannia",
        "description": "Soft baked whole wheat bread rich in dietary fibre.",
        "price": 55.0,
        "store_qtys": [22, 20, 18, 20],
    },
    {
        "sku": "BISCUIT-PARLE-HIDE-SEEK",
        "name": "Parle Hide & Seek Chocolate Chip Cookies 100g",
        "category": "Bakery & Biscuits",
        "brand": "Parle",
        "description": "Crunchy cookies loaded with rich choco chips.",
        "price": 30.0,
        "store_qtys": [45, 40, 35, 30],
    },
    {
        "sku": "VEG-ONION-1KG",
        "name": "Fresh Nashik Onion 1kg",
        "category": "Fruits & Vegetables",
        "brand": "Farm Fresh",
        "description": "Handpicked medium-sized red onions sorted for daily cooking.",
        "price": 42.0,
        "store_qtys": [50, 45, 40, 40],
    },
    {
        "sku": "VEG-TOMATO-500G",
        "name": "Fresh Hybrid Tomato 500g",
        "category": "Fruits & Vegetables",
        "brand": "Farm Fresh",
        "description": "Juicy, ripe red tomatoes sourced directly from local farms.",
        "price": 24.0,
        "store_qtys": [40, 35, 30, 35],
    },
    {
        "sku": "FRUIT-BANANA-ROBUSTA-6PC",
        "name": "Robusta Banana (6 pcs)",
        "category": "Fruits & Vegetables",
        "brand": "Farm Fresh",
        "description": "Naturally ripened sweet Robusta bananas, rich in potassium.",
        "price": 39.0,
        "store_qtys": [30, 28, 25, 25],
    },
    {
        "sku": "CHIPS-LAYS-MAGIC-MASALA",
        "name": "Lay's India's Magic Masala Potato Chips 50g",
        "category": "Snacks & Munchies",
        "brand": "Lay's",
        "description": "Crispy potato chips seasoned with signature Indian spices.",
        "price": 20.0,
        "store_qtys": [60, 50, 55, 45],
    },
    {
        "sku": "SNACK-HALDIRAM-BHUJIA-200G",
        "name": "Haldiram's Nagpur Aloo Bhujia 200g",
        "category": "Snacks & Munchies",
        "brand": "Haldiram's",
        "description": "Crispy gram flour and potato noodle namkeen with tangy spices.",
        "price": 56.0,
        "store_qtys": [35, 30, 40, 30],
    },
    {
        "sku": "DRINK-COKE-ZERO-300ML",
        "name": "Coca-Cola Zero Sugar Can 300ml",
        "category": "Cold Drinks & Juices",
        "brand": "Coca-Cola",
        "description": "Great Coca-Cola taste with zero sugar and zero calories.",
        "price": 40.0,
        "store_qtys": [40, 40, 35, 30],
    },
    {
        "sku": "JUICE-TROPICANA-ORANGE-1L",
        "name": "Tropicana 100% Orange Juice 1L",
        "category": "Cold Drinks & Juices",
        "brand": "Tropicana",
        "description": "100% pure squeezed orange juice with no added sugar.",
        "price": 145.0,
        "store_qtys": [18, 15, 20, 15],
    },
    {
        "sku": "CHOC-CADBURY-SILK-60G",
        "name": "Cadbury Dairy Milk Silk Chocolate Bar 60g",
        "category": "Sweet Tooth",
        "brand": "Cadbury",
        "description": "Smooth, creamy and melt-in-the-mouth milk chocolate.",
        "price": 85.0,
        "store_qtys": [30, 25, 35, 25],
    },
    {
        "sku": "ICE-AMUL-VANILLA-750ML",
        "name": "Amul Real Milk Vanilla Magic Ice Cream 750ml",
        "category": "Sweet Tooth",
        "brand": "Amul",
        "description": "Rich and creamy vanilla ice cream made with real milk.",
        "price": 150.0,
        "store_qtys": [15, 12, 14, 12],
    },
    {
        "sku": "TEA-TATA-GOLD-250G",
        "name": "Tata Tea Gold Assam Tea with Long Leaves 250g",
        "category": "Tea, Coffee & Health Drinks",
        "brand": "Tata",
        "description": "Rich AssamCTC tea blended with 15% gently rolled aromatic long leaves.",
        "price": 165.0,
        "store_qtys": [20, 20, 22, 18],
    },
    {
        "sku": "COFFEE-NESCAFE-CLASSIC-45G",
        "name": "Nescafe Classic Instant Coffee Jar 45g",
        "category": "Tea, Coffee & Health Drinks",
        "brand": "Nescafe",
        "description": "100% pure instant coffee made from selected roasted coffee beans.",
        "price": 170.0,
        "store_qtys": [16, 15, 18, 15],
    },
    {
        "sku": "ATTA-AASHIRVAAD-5KG",
        "name": "Aashirvaad Shudh Chakki Whole Wheat Atta 5kg",
        "category": "Atta, Rice & Dal",
        "brand": "Aashirvaad",
        "description": "100% whole wheat flour ground using traditional chakki process for soft rotis.",
        "price": 265.0,
        "store_qtys": [15, 15, 12, 15],
    },
]


async def seed_initial_data() -> None:
    """
    Idempotently seed initial Dark Stores, Catalog Products, DarkStoreStock, and Demo Users
    when the database has no dark stores or items.
    """
    try:
        async with AsyncSessionLocal() as db:
            # 1. Seed Dark Stores if none exist
            store_count = (await db.execute(select(func.count(DarkStore.id)))).scalar_one()
            stores_by_code: dict[str, DarkStore] = {}
            if store_count == 0:
                for s_data in INITIAL_STORES:
                    store = DarkStore(**s_data)
                    db.add(store)
                    stores_by_code[store.code] = store
                await db.flush()
                logger.info(f"Seeded {len(INITIAL_STORES)} initial Dark Stores")
            else:
                existing_stores = (await db.execute(select(DarkStore))).scalars().all()
                stores_by_code = {s.code: s for s in existing_stores}

            # 2. Seed Catalog Products & Per-Store Stock if no items exist
            item_count = (await db.execute(select(func.count(InventoryItem.id)))).scalar_one()
            if item_count == 0:
                ordered_stores = [
                    stores_by_code.get(s["code"])
                    for s in INITIAL_STORES
                    if s["code"] in stores_by_code
                ]
                for p_data in INITIAL_PRODUCTS:
                    store_qtys = p_data["store_qtys"]
                    total_qty = sum(store_qtys)
                    item = InventoryItem(
                        sku=p_data["sku"],
                        name=p_data["name"],
                        category=p_data["category"],
                        brand=p_data["brand"],
                        description=p_data["description"],
                        price=p_data["price"],
                        available_qty=total_qty,
                    )
                    db.add(item)
                    await db.flush()

                    for idx, store in enumerate(ordered_stores):
                        if store is not None and idx < len(store_qtys):
                            db.add(
                                DarkStoreStock(
                                    store_id=store.id,
                                    item_id=item.id,
                                    available_qty=store_qtys[idx],
                                )
                            )
                logger.info(f"Seeded {len(INITIAL_PRODUCTS)} initial catalog products & store stocks")

            # 3. Ensure Demo Admin and Demo Customer accounts exist
            admin_exists = (
                await db.execute(select(User).where(User.email == "admin@quickkart.com"))
            ).scalar_one_or_none()
            if not admin_exists:
                admin_pw = await hash_password_async("admin1234")
                db.add(
                    User(
                        email="admin@quickkart.com",
                        full_name="QuickKart Admin",
                        hashed_password=admin_pw,
                        is_admin=True,
                    )
                )

            demo_exists = (
                await db.execute(select(User).where(User.email == "demo@quickkart.com"))
            ).scalar_one_or_none()
            if not demo_exists:
                demo_pw = await hash_password_async("demo1234")
                demo_user = User(
                    email="demo@quickkart.com",
                    full_name="Aarav Sharma",
                    hashed_password=demo_pw,
                    is_admin=False,
                )
                db.add(demo_user)
                await db.flush()
                db.add(
                    Address(
                        user_id=demo_user.id,
                        label="Home",
                        line1="42, 12th Main Road, HAL 2nd Stage, Indiranagar",
                        city="Bengaluru",
                        pincode="560038",
                        latitude=12.9719,
                        longitude=77.6412,
                        is_default=True,
                    )
                )

            await db.commit()
    except Exception:
        logger.exception("Initial data seeding failed (continuing startup)")

