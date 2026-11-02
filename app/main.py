"""App entrypoint: creates the FastAPI app, configures structured logging, wires up middlewares and routers."""
import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from sqlalchemy import text

from app import models  # noqa: F401  (registers all tables on Base.metadata)
from app.api.routes import analytics, auth, cart, delivery, items, payments, stores, users
from app.core.database import Base, engine
from app.core.logging import get_logger, setup_logging
from app.core.middleware import register_middlewares
from app.services.order_service import run_order_expiry_worker
from app.services.seed_service import seed_initial_data

# Initialize structured logging before anything else
setup_logging()
logger = get_logger("app.main")

_STARTUP_SCHEMA_UPGRADES = (
    "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS category VARCHAR(50)",
    "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS brand VARCHAR(50)",
    "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS description VARCHAR(500)",
    "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS image_url VARCHAR(500)",
    "CREATE INDEX IF NOT EXISTS ix_inventory_items_category ON inventory_items (category)",
    "CREATE INDEX IF NOT EXISTS ix_inventory_items_brand ON inventory_items (brand)",
    "CREATE INDEX IF NOT EXISTS ix_inventory_items_name ON inventory_items (name)",
    "CREATE INDEX IF NOT EXISTS ix_inventory_items_category_stock ON inventory_items (category, available_qty)",
    "ALTER TABLE addresses ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
    "ALTER TABLE addresses ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS store_id INTEGER REFERENCES dark_stores(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS ix_orders_store_id ON orders (store_id)",
)


# Automatically create tables and apply idempotent column additions on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for ddl in _STARTUP_SCHEMA_UPGRADES:
            await conn.execute(text(ddl))

    await seed_initial_data()
    expiry_task = asyncio.create_task(run_order_expiry_worker(), name="order-expiry-worker")
    logger.info("Application startup complete.")
    try:
        yield
    finally:
        expiry_task.cancel()
        with suppress(asyncio.CancelledError):
            await expiry_task
        await engine.dispose()
        logger.info("Application shutting down.")


app = FastAPI(title="Blinkit Inventory Microservice MVP", lifespan=lifespan)

# Register all 6 middlewares (TrustedHost, CORS, RequestID, AccessLog, RateLimit, SelectiveGZip)
register_middlewares(app)

# Register API routers
@app.get("/health", tags=["health"])
async def health_check():
    """Liveness/readiness probe used by Docker & orchestrators: verifies the DB is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"status": "unhealthy", "database": str(exc)[:200]})
    return {"status": "ok", "database": "ok"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(stores.router)
app.include_router(items.router)
app.include_router(cart.router)
app.include_router(delivery.router)
app.include_router(payments.router)
app.include_router(analytics.router)
