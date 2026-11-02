# Blinkit Quick-Commerce Microservice (MVP)

A high-concurrency, asynchronous **FastAPI** service for a quick-commerce store (Blinkit-style). It manages product inventory, shopping carts, atomic checkout, order tracking, and user personalization—**guaranteeing no overselling or race conditions** under concurrent customer traffic.

---

## ✨ Features

- **Multi-Dark-Store & Geo-Serviceability (`/stores`)**:
  - **Neighborhood Dark Stores (`dark_stores`)**: Manage hyperlocal micro-warehouses with GPS coordinates (`latitude`, `longitude`), `service_radius_km` (default `3.0 km`), and `base_prep_minutes` (default `3 min`).
  - **Per-Store Inventory (`dark_store_stocks`)**: Track SKU stock per dark store while automatically keeping aggregate `inventory_items.available_qty` in sync.
  - **Haversine Geo-Serviceability Check (`GET /stores/serviceability`)**: Given customer GPS coordinates (`lat`, `lng`), a `pincode`, or a saved `address_id`, finds the nearest active dark store within its delivery radius, computes exact distance in km, and estimates delivery ETA ($\text{ETA} = \text{base\_prep\_minutes} + \lceil \text{distance\_km} \times 3.0 \rceil$).
  - **End-to-End Store Scoping**: Search (`GET /items/search`), autocomplete, cart (`GET /me/cart`), checkout (`POST /me/cart/checkout`), order cancellation/expiry stock restoration, and 1-Hz live GPS delivery tracking all natively support dark-store-specific stock and pickup coordinates.
- **Product Catalog, Search & Discovery**:
  - Add & update products with SKU, name, category, brand, description, price, and starting quantity.
  - **Multi-Token Relevance Search (`GET /items/search`)**: Case-insensitive search across name, SKU, brand, category, and description with weighted relevance ranking (exact match $\rightarrow$ prefix match $\rightarrow$ substring match $\rightarrow$ in-stock boost).
  - **Faceted Filtering & Sorting**: Filter by `category`, `brand`, `min_price`, `max_price`, `in_stock`, or batch `skus`; sort by `relevance`, `price_asc`, `price_desc`, `name_asc`, `name_desc`, or `stock_desc`.
  - **Search Bar Autocomplete (`GET /items/suggest`)**: Instant typeahead returning matching products, categories, and brands.
  - **Category & Brand Facets (`GET /items/categories`, `GET /items/brands`)**: Browse categories and brands with total and in-stock item counts.
  - **"Frequently Bought Together" & Similar Items (`GET /items/{sku}/similar`)**: Co-purchase recommendations from `order_items` with category/brand fallback.
  - Instant stock updates: customer direct-buy (negative delta) or admin restock (positive delta).
- **Shopping Cart & Multi-Item Checkout**:
  - Add/update item quantities in cart with live availability validation.
  - Cart view provides live item prices, stock alerts, and subtotal calculation.
  - Atomically checkout cart into an order (empty cart + deduct stock + create order in one transaction).
  - Deadlock prevention using sorted row-level locking (`SELECT ... FOR UPDATE` ordered by item ID).
- **Concurrency & Overselling Prevention**:
  - Pessimistic locking (`SELECT ... FOR UPDATE`) ensures two concurrent checkouts never oversell stock.
  - Database-level `CHECK (available_qty >= 0)` constraint guarantees stock can never go negative.
- **Payment Gateway & Cash on Delivery (COD)**:
  - Unified `PaymentGateway` interface with **Razorpay** and **Mock Simulator** providers.
  - Multi-method support: **UPI**, **Credit/Debit Cards**, **Digital Wallets**, and **Cash on Delivery (COD)**.
  - Cryptographic HMAC-SHA256 signature verification for external payment webhooks.
  - Instant COD confirmation or Gateway order token generation for UPI intent / card payment modal.
  - Automated stock restoration if payment fails or order is canceled.
  - Sandbox test simulation endpoints to test payment success and failure flows without real money.
- **Order Management & Rich Purchase History**:
  - Multi-line orders with price snapshotting at purchase time (`unit_price`).
  - Saved delivery address association (`SET NULL` on address deletion to preserve order history).
  - Enriched order history with live **delivery status**, **tracking ID**, **payment status**, and **payment method**.
  - **1-Click Reorder**: `POST /me/orders/{order_id}/reorder` adds all in-stock items from a past order back into active cart.
- **Real-Time Delivery & GPS Tracking**:
  - **Asynchronous 3rd-Party Delivery Dispatch**: Orders trigger non-blocking delivery partner dispatch in the background without slowing down customer checkout.
  - **Real-Time GPS Tracking & Live Stream (1-Hz SSE)**: Server-Sent Events (`GET /me/orders/{order_id}/tracking/stream`) push live GPS coordinates, rider details, and ETA every second directly to the user's map.
  - **Zero-DB Bloat GPS Architecture**: Ephemeral 1-Hz coordinates stream from in-memory state; only major milestones (`ASSIGNED`, `REACHED_DARK_STORE`, `PICKED_UP`, `OUT_FOR_DELIVERY`, `DELIVERED`) are persisted to PostgreSQL.
- **Business Analytics & Real-Time Reporting**:
  - Executive KPI summary (`GET /admin/analytics/summary`): Gross Merchandise Value (GMV), Average Order Value (AOV), total order count, payment distribution (UPI vs COD vs Cards), and active in-transit deliveries.
  - Top-selling product velocity (`GET /admin/analytics/top-selling`): Ranked by sales volume and revenue.
  - Inventory health & stock-out detection (`GET /admin/analytics/inventory-health`): Total inventory valuation, available units, and replenishment alerts.
- **User Authentication & Personalization**:
  - User registration and login using JWT tokens and bcrypt password hashing.
  - Role-based access control (Admin vs. Authenticated User vs. Public).
  - Wishlist / Favorites per user.
  - Multiple delivery address management with default address support.
- **Developer-Friendly**:
  - Clean layered modular architecture (API routes, services, schemas, models, core).
  - Auto table creation on startup.
  - Interactive Swagger UI documentation at `/docs`.

---

## 🧱 Tech Stack

| Layer          | Technology                    |
|----------------|-------------------------------|
| Web Framework  | FastAPI 0.115                 |
| ASGI Server    | Uvicorn                       |
| ORM            | SQLAlchemy 2.0 (AsyncIO)      |
| Database Driver| asyncpg                       |
| Database       | PostgreSQL                    |
| Validation     | Pydantic v2                   |
| Security & Auth| PyJWT, Bcrypt                 |

---

## 📁 Project Structure

```
Blink It/
├── app/
│   ├── main.py                 # FastAPI application, startup lifespan & router registration
│   ├── api/
│   │   ├── deps.py             # Auth dependencies (get_current_user, require_admin)
│   │   └── routes/
│   │       ├── analytics.py    # /admin/analytics (KPI summary, top SKUs, inventory health)
│   │       ├── auth.py         # /auth (register, login)
│   │       ├── cart.py         # /me/cart (cart management & checkout)
│   │       ├── delivery.py     # /me/orders/.../tracking (REST snapshot & SSE live stream)
│   │       ├── items.py        # /items (inventory management & stock updates)
│   │       ├── payments.py     # /me/orders/.../payments (initiate, test simulate, & webhooks)
│   │       ├── stores.py       # /stores (dark store CRUD, geo-serviceability & per-store stock)
│   │       └── users.py        # /me (profile, favorites, orders, reorder, addresses)
│   ├── core/
│   │   ├── config.py           # Configuration & environment variables
│   │   ├── database.py         # Async engine, sessionmaker, Base, get_db dependency
│   │   ├── logging.py          # Structured JSON logger & context tracking
│   │   ├── middleware.py       # Stack of 6 middlewares (RateLimit, RequestID, ProcessTime, etc.)
│   │   ├── security.py         # Password hashing (bcrypt) & JWT token handling
│   │   └── tasks.py            # Background task manager with strong references & error logging
│   ├── models/
│   │   ├── cart.py             # CartItem model
│   │   ├── delivery.py         # DeliveryAssignment model (milestones & partner tracking)
│   │   ├── item.py             # InventoryItem model
│   │   ├── order.py            # Order and OrderItem models
│   │   ├── payment.py          # Payment transaction model
│   │   ├── store.py            # DarkStore and DarkStoreStock models
│   │   └── user.py             # User, Favorite, Address models
│   ├── schemas/
│   │   ├── analytics.py        # Business metrics & KPI response schemas
│   │   ├── cart.py             # Cart & checkout Pydantic schemas
│   │   ├── delivery.py         # Delivery snapshot, rider info & location schemas
│   │   ├── item.py             # Item & stock update Pydantic schemas
│   │   ├── order.py            # Order, order line & reorder Pydantic schemas
│   │   ├── payment.py          # Payment initiation, response & simulation schemas
│   │   ├── store.py            # DarkStore, serviceability & per-store stock schemas
│   │   └── user.py             # User, address, favorite Pydantic schemas
│   └── services/
│       ├── analytics_service.py# SQL aggregation queries for GMV, AOV & inventory health
│       ├── delivery_service.py # 3rd-party logistics adapter, GPS simulator & SSE generator
│       ├── item_service.py     # Inventory operations, faceted search & atomic stock changes
│       ├── order_service.py    # Multi-item checkout, order placement, expiry & history
│       ├── payment_service.py  # Razorpay & Mock payment gateways, COD, webhook verifications
│       └── store_service.py    # Dark store CRUD, Haversine serviceability & per-store stock
├── requirements.txt            # Project dependencies
└── README.md
```

---

## 🗄️ Data Model

### Tables

1. **`inventory_items`**
   - `id`: Integer (PK, indexed)
   - `sku`: String(50) (Unique, indexed)
   - `name`: String(100) (Required, indexed)
   - `category`: String(50), nullable, indexed (e.g., `"Dairy & Breakfast"`, `"Snacks & Munchies"`)
   - `brand`: String(50), nullable, indexed (e.g., `"Nandini"`, `"Amul"`)
   - `description`: String(500), nullable
   - `price`: Numeric(10, 2) (Required, > 0)
   - `available_qty`: Integer (Required, default `0`, `CHECK (available_qty >= 0)`)

2. **`cart_items`**
   - `id`: Integer (PK)
   - `user_id`: ForeignKey(`users.id`, CASCADE, indexed)
   - `item_id`: ForeignKey(`inventory_items.id`, CASCADE)
   - `quantity`: Integer (Required, `CHECK (quantity > 0)`)
   - `added_at`: DateTime (Timezone-aware, default `now()`)
   - `UNIQUE (user_id, item_id)`

3. **`orders`**
   - `id`: Integer (PK)
   - `user_id`: ForeignKey(`users.id`, CASCADE, indexed)
   - `address_id`: ForeignKey(`addresses.id`, SET NULL, nullable)
   - `total`: Numeric(10, 2) (Required)
   - `status`: String(20) (Default `"PLACED"`)
   - `created_at`: DateTime (Timezone-aware, default `now()`)

4. **`order_items`**
   - `id`: Integer (PK)
   - `order_id`: ForeignKey(`orders.id`, CASCADE, indexed)
   - `item_id`: ForeignKey(`inventory_items.id`)
   - `quantity`: Integer (Required, `CHECK (quantity > 0)`)
   - `unit_price`: Numeric(10, 2) (Snapshot of price at purchase time)

5. **`users`**
   - `id`: Integer (PK, indexed)
   - `email`: String(255) (Unique, indexed, normalized lowercase)
   - `full_name`: String(100)
   - `hashed_password`: String(255)
   - `is_admin`: Boolean (Default `False`)
   - `created_at`: DateTime (Timezone-aware, default `now()`)

6. **`favorites`**
   - `id`: Integer (PK)
   - `user_id`: ForeignKey(`users.id`, CASCADE, indexed)
   - `item_id`: ForeignKey(`inventory_items.id`, CASCADE)
   - `created_at`: DateTime (Timezone-aware, default `now()`)
   - `UNIQUE (user_id, item_id)`

7. **`addresses`**
   - `id`: Integer (PK)
   - `user_id`: ForeignKey(`users.id`, CASCADE, indexed)
   - `label`: String(50) (e.g. `"Home"`, `"Office"`)
   - `line1`: String(255)
   - `line2`: String(255), nullable
   - `city`: String(100)
   - `pincode`: String(10) (6-digit format validated)
   - `is_default`: Boolean (Default `False`)

8. **`delivery_assignments`**
   - `id`: Integer (PK)
   - `order_id`: ForeignKey(`orders.id`, CASCADE, unique, indexed)
   - `tracking_id`: String(100) (Unique, indexed, 3rd-party logistics ID)
   - `partner_name`: String(50) (Default `"QuickLogistics"`)
   - `rider_name`: String(100)
   - `rider_phone`: String(20)
   - `vehicle_type`: String(50)
   - `status`: String(30) (`ASSIGNED`, `REACHED_DARK_STORE`, `PICKED_UP`, `OUT_FOR_DELIVERY`, `DELIVERED`)
   - `pickup_address`: String(255)
   - `delivery_address`: String(255)
   - `assigned_at`: DateTime (Timezone-aware, default `now()`)
   - `delivered_at`: DateTime (Timezone-aware, nullable)

9. **`payments`**
   - `id`: Integer (PK)
   - `order_id`: ForeignKey(`orders.id`, CASCADE, indexed)
   - `user_id`: ForeignKey(`users.id`, CASCADE, indexed)
   - `amount`: Numeric(10, 2)
   - `currency`: String(10) (Default `"INR"`)
   - `payment_method`: String(30) (`UPI`, `CARD`, `COD`, `WALLET`)
   - `status`: String(30) (`PENDING`, `SUCCESS`, `FAILED`, `REFUNDED`)
   - `gateway_name`: String(50) (`RAZORPAY`, `MOCK`, `COD`)
   - `gateway_order_id`: String(100), nullable, indexed
   - `gateway_payment_id`: String(100), nullable, indexed
   - `error_reason`: String(255), nullable
   - `created_at`: DateTime (Timezone-aware, default `now()`)
   - `updated_at`: DateTime (Timezone-aware, default `now()`)

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.11+
- A running PostgreSQL instance

### 2. Create the Database
```sql
CREATE DATABASE inventory_db;
```

### 3. Setup Virtual Environment (Windows / PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Configuration & Environment Variables

Create or set environment variables as needed:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://sde_user:sde_password@localhost:5432/inventory_db` | Async PostgreSQL connection string |
| `JWT_SECRET` | `dev-only-insecure-secret-change-me` | Secret for signing JWT access tokens |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT token lifetime |
| `ADMIN_EMAILS` | *(empty)* | Comma-separated emails granted admin role on registration |
| `ALLOWED_HOSTS` | `*` | Comma-separated list of allowed hostnames for `TrustedHostMiddleware` |
| `CORS_ORIGINS` | `*` | Comma-separated list of allowed origins for `CORSMiddleware` |
| `RATE_LIMIT_PER_MINUTE` | `60` | Maximum requests per minute per IP address |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_FORMAT` | `json` | Structured output format (`json` or `text`) |
| `PAYMENT_GATEWAY` | `MOCK` | Gateway provider (`MOCK` or `RAZORPAY`) |
| `RAZORPAY_KEY_ID` | `rzp_test_mock_key` | Razorpay Key ID |
| `RAZORPAY_KEY_SECRET` | `mock_key_secret` | Razorpay Key Secret |
| `RAZORPAY_WEBHOOK_SECRET` | `mock_webhook_secret` | Webhook secret for HMAC signature verification |

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/inventory_db"
$env:JWT_SECRET = "super-secret-random-key"
$env:ADMIN_EMAILS = "admin@example.com"
$env:LOG_FORMAT = "json"
$env:RATE_LIMIT_PER_MINUTE = "100"
```

### 5. Run the Server
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```
Open **http://127.0.0.1:8000/docs** to explore and test the interactive OpenAPI documentation.

---

## 📡 API Reference

### 🔐 Authentication (`/auth`)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/auth/register` | Public | Register a new user account |
| `POST` | `/auth/login` | Public | Login (OAuth2 password form) and receive JWT |

### 🏪 Dark Stores & Geo-Serviceability (`/stores`)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/stores` | Admin | Create a new neighborhood Dark Store with GPS coordinates and `service_radius_km` |
| `GET` | `/stores` | Public | List Dark Stores (optionally filtered by `?city=`, `?pincode=`, `?active_only=true`) |
| `GET` | `/stores/serviceability` | Public | Check if customer GPS (`?lat=&lng=`), `?pincode=`, or `?address_id=` is within an active store's radius; returns nearest store, `distance_km`, and `eta_minutes` |
| `GET` | `/stores/{store_id}` | Public | Get details of a specific Dark Store |
| `PATCH` | `/stores/{store_id}` | Admin | Update Dark Store radius, prep time, active status, or coordinates |
| `GET` | `/stores/{store_id}/items` | Public | Browse catalog items and their real-time stock at a specific Dark Store |
| `PATCH` | `/stores/{store_id}/items/{sku}/stock` | Admin | Restock or adjust stock for a SKU at a specific Dark Store (synchronizes global stock) |

### 📦 Product Catalog, Search & Inventory (`/items`)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/items` | Admin | Create a new inventory item (with optional `category`, `brand`, `description`) |
| `GET` | `/items` | Public | List/filter items (`?q=&category=&brand=&min_price=&max_price=&in_stock=&sort_by=&limit=10&offset=0`) |
| `GET` | `/items/search` | Public | Paginated search & filter with relevance ranking and total count (`total`, `has_more`, `items`) |
| `GET` | `/items/suggest` | Public | Search bar typeahead autocomplete (`?q=milk&limit=8`) returning products, categories, and brands |
| `GET` | `/items/categories` | Public | List all categories with `total_items` and `in_stock_items` counts |
| `GET` | `/items/brands` | Public | List all brands (optionally filtered by `?category=`) with item counts |
| `GET` | `/items/{sku}` | Public | Retrieve product details & real-time stock by SKU |
| `PATCH` | `/items/{sku}` | Admin | Update product metadata (`name`, `category`, `brand`, `description`, `price`) |
| `GET` | `/items/{sku}/similar` | Public | Retrieve "Frequently Bought Together" and similar items in the same category/brand |
| `PATCH` | `/items/{sku}/stock` | User / Admin | Direct purchase (delta < 0) or Restock (admin only, delta > 0) |

### 🛒 Shopping Cart (`/me/cart`)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/me/cart` | User | View current cart with live prices and stock availability |
| `PUT` | `/me/cart/{sku}` | User | Set item quantity in cart (`quantity: 1..50`) |
| `DELETE` | `/me/cart/{sku}` | User | Remove item from cart |
| `DELETE` | `/me/cart` | User | Clear entire cart |
| `POST` | `/me/cart/checkout` | User | Atomic checkout: locks stock, deducts inventory, creates order, and clears cart |

### 👤 User Profile, Favorites & Addresses (`/me`)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/me` | User | Get current logged-in user profile |
| `GET` | `/me/favorites` | User | List favorite items |
| `PUT` | `/me/favorites/{sku}` | User | Add SKU to favorites (idempotent) |
| `DELETE` | `/me/favorites/{sku}` | User | Remove SKU from favorites |
| `GET` | `/me/addresses` | User | List saved delivery addresses (default first) |
| `POST` | `/me/addresses` | User | Add a new delivery address |
| `DELETE` | `/me/addresses/{address_id}` | User | Delete a delivery address |

### 📋 Orders & Purchase History (`/me/orders`)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/me/orders` | User | View paginated order history with live delivery & payment status |
| `GET` | `/me/orders/{order_id}` | User | View detailed order receipt, line items, and delivery address |
| `POST` | `/me/orders/{order_id}/cancel` | User | Cancel an unpaid order and immediately release its reserved stock |
| `POST` | `/me/orders/{order_id}/reorder` | User | **1-Click Reorder**: Copies in-stock items from this past order directly into active cart |

### 🛵 Real-Time Delivery Tracking (`/me/orders`)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/me/orders/{order_id}/tracking` | User | REST snapshot: current rider info, GPS coordinates, status, and ETA |
| `GET` | `/me/orders/{order_id}/tracking/stream` | User | **Server-Sent Events (SSE)**: Streams live GPS updates and milestones **every 1 second** directly to the user's map until delivered |

### 💳 Payments & Gateway Integration

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/me/orders/{order_id}/payments` | User | Initiate payment (`payment_method`: `UPI`, `CARD`, `COD`, `WALLET`). Instant confirmation for COD, or returns gateway order token for online checkout |
| `GET` | `/me/orders/{order_id}/payments` | User | View all payment attempts and status for an order |
| `POST` | `/me/orders/{order_id}/payments/{payment_id}/simulate-success` | User | Sandbox test endpoint: simulates successful gateway payment, marks order `PAID`, dispatches delivery |
| `POST` | `/me/orders/{order_id}/payments/{payment_id}/simulate-failure` | User | Sandbox test endpoint: simulates failed payment, marks order `PAYMENT_FAILED`, and **automatically restores reserved stock** |
| `POST` | `/payments/webhook` | Gateway / Public | External payment gateway webhook (Razorpay/Mock) with cryptographic HMAC-SHA256 signature verification |

### 📊 Business Analytics (`/admin/analytics`)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/admin/analytics/summary` | Admin | Real-time executive dashboard: GMV, Total Orders, Paid Orders, Average Order Value (AOV), payment method breakdown, and active deliveries |
| `GET` | `/admin/analytics/top-selling` | Admin | Top-selling SKUs ranked by units sold and generated revenue (`?limit=10`) |
| `GET` | `/admin/analytics/inventory-health` | Admin | Inventory valuation, total units, out-of-stock count, and low-stock replenishment warnings |

---

## 🛡️ Middlewares & Structured Logging

The application includes 6 stacked middlewares registered in optimal execution order:

1. **`TrustedHostMiddleware`**: Protects against HTTP Host header attacks by strictly validating allowed hosts (`ALLOWED_HOSTS`).
2. **`CORSMiddleware`**: Handles preflight `OPTIONS` requests, permits configured origins (`CORS_ORIGINS`), and exposes headers (`X-Request-ID`, `X-Process-Time`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`).
3. **`GZipMiddleware`**: Compresses HTTP responses greater than 1,000 bytes, reducing bandwidth consumption for large catalog listings.
4. **`RateLimitingMiddleware`**: Sliding-window in-memory rate limiting per client IP (default: 60 req/min, configurable via `RATE_LIMIT_PER_MINUTE`). Rejects floods with `429 Too Many Requests` and standard `Retry-After` headers.
5. **`RequestIDMiddleware`**: Generates or forwards a unique `X-Request-ID` (UUID) per request, storing it in `contextvars` so all application logs are correlated to the request.
6. **`ProcessTimeAndLoggingMiddleware`**: Profiles latency (`X-Process-Time` in ms) and emits structured JSON logs.

### Structured Logging Format

When `LOG_FORMAT=json`, log records are emitted as JSON lines compatible with Datadog, ELK, CloudWatch, and GCP Logging:

```json
{
  "timestamp": "2026-11-02T07:07:08.752265+00:00",
  "level": "INFO",
  "logger": "app.access",
  "message": "HTTP POST /me/cart/checkout - 201 (14.2ms)",
  "request_id": "a98fdc81-8b3a-44c0-bf32-e02bb2ef1b93",
  "method": "POST",
  "path": "/me/cart/checkout",
  "status_code": 201,
  "process_time_ms": 14.2,
  "client_ip": "127.0.0.1",
  "user_agent": "Mozilla/5.0..."
}
```

---

## 🛵 Real-Time Delivery Partner Architecture

Quick-commerce delivery apps require second-by-second live location updates without causing database write amplification or hitting 3rd-party logistics API rate limits.

### How it Works:
1. **Asynchronous Dispatch**: Checkout commits immediately. The dispatch call to the third-party delivery partner runs in the background, keeping checkout response latency $< 30\text{ms}$.
2. **Ephemeral In-Memory GPS Engine**: High-frequency 1-Hz GPS ticks stream from an in-memory active tracking state directly to connected users via **Server-Sent Events (SSE)**.
3. **Milestone-Only DB Persistence**: Only significant lifecycle transitions are committed to PostgreSQL:
   - `ASSIGNED` $\rightarrow$ `REACHED_DARK_STORE` $\rightarrow$ `PICKED_UP` $\rightarrow$ `OUT_FOR_DELIVERY` $\rightarrow$ `DELIVERED`
4. **Provider Abstraction**: A clean `DeliveryProvider` interface separates business logic from partner-specific implementations. The built-in `SimulatorDeliveryProvider` models dark store dispatch and smooth route interpolation, and can be swapped for Dunzo, Shadowfax, or Borzo by implementing the interface.

---

## 💳 Payment Gateway & Cash on Delivery (COD) Architecture

Quick-commerce orders require flexible payment options and bulletproof stock recovery if an online payment fails.

### Supported Flows:
1. **Cash on Delivery (COD)**:
   - User selects `payment_method: COD`.
   - Order transitions immediately to `CONFIRMED`.
   - Delivery partner dispatch is triggered in the background.
2. **Online Payment (UPI, Cards, Wallets via Razorpay / Mock)**:
   - Order transitions to `PENDING_PAYMENT`.
   - The gateway generates a payment order token for frontend display (Razorpay checkout modal, UPI intent, or QR).
   - Upon customer payment, the gateway triggers a signed webhook (`POST /payments/webhook`) verified with HMAC-SHA256.
   - Upon success: order transitions to `PAID` and delivery partner is dispatched.
   - Upon failure / decline: order transitions to `PAYMENT_FAILED` and **reserved inventory stock is atomically restored**.
3. **Local Testing & Simulation**:
   - `POST /me/orders/{order_id}/payments/{payment_id}/simulate-success`: Simulates a webhook success ping.
   - `POST /me/orders/{order_id}/payments/{payment_id}/simulate-failure`: Simulates a failure and verifies that items are credited back to inventory.

---

## 🔒 How Overselling & Race Conditions Are Prevented

1. **Pessimistic Row-Level Locking (`SELECT ... FOR UPDATE`)**:
   During direct purchases or cart checkout, all involved items are queried with `FOR UPDATE`. Any competing request attempting to checkout or modify the same products waits until the active transaction finishes.
2. **Deadlock Prevention via Sorted Lock Acquisition**:
   When ordering multiple items in cart checkout, locks are always acquired in ascending order of `InventoryItem.id`. This ensures concurrent multi-item checkouts cannot cause database deadlocks.
3. **Atomic All-or-Nothing Transactions**:
   All stock checks, inventory deductions, order item recordings, and cart cleanups are executed inside a single async transaction. If any item is out of stock, the transaction aborts with `409 Conflict`, leaving stock untouched.
4. **Database-Level Guardrails**:
   A PostgreSQL `CHECK (available_qty >= 0)` constraint serves as the final barrier, guaranteeing stock cannot go negative even under unforeseen edge cases.

---

## 🧪 Testing

To run the application checks:
```powershell
.\.venv\Scripts\python.exe -c "import app.main; print('Application configured successfully!')"
```
