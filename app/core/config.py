"""Central settings: every env var the app reads lives here."""
import os


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://sde_user:sde_password@localhost:5432/inventory_db"
)
# Log every SQL statement (routed through the structured logger). Keep off in production.
DB_ECHO = _env_bool("DB_ECHO")

# IMPORTANT: set a long random JWT_SECRET in any real deployment.
DEFAULT_JWT_SECRET = "dev-only-insecure-secret-change-me"
JWT_SECRET = os.getenv("JWT_SECRET", DEFAULT_JWT_SECRET)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Comma-separated emails that get admin rights when they register.
ADMIN_EMAILS = {
    e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
}

# --- Middleware & Logging Settings ---
# Allowed Hosts for TrustedHostMiddleware (comma-separated, default "*" allows all)
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()]

# CORS allowed origins (comma-separated, default "*")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

# In-memory sliding-window rate limit (requests per client IP per minute)
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

# Logging settings
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # "json" or "text"

# --- Payment Gateway Settings ---
PAYMENT_GATEWAY = os.getenv("PAYMENT_GATEWAY", "MOCK").upper()  # "RAZORPAY" or "MOCK"
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_mock_key")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "mock_key_secret")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "mock_webhook_secret")

# Sandbox endpoints (simulate-success / simulate-failure) are only exposed with the MOCK gateway.
PAYMENT_SANDBOX_ENABLED = PAYMENT_GATEWAY == "MOCK"

# --- Order lifecycle ---
# Unpaid orders hold reserved stock for this long; after that the stock is released.
PAYMENT_TIMEOUT_MINUTES = int(os.getenv("PAYMENT_TIMEOUT_MINUTES", "15"))
# How often the background sweeper looks for expired unpaid orders.
ORDER_EXPIRY_SWEEP_SECONDS = int(os.getenv("ORDER_EXPIRY_SWEEP_SECONDS", "60"))
