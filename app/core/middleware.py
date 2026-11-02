"""Custom middlewares for Blinkit microservice.

All custom middlewares are pure ASGI (not BaseHTTPMiddleware): lower per-request overhead,
no extra task per request, and streaming responses (SSE) pass straight through.

Includes:
1. Request ID (Correlation ID) tracking via contextvars
2. Access logging + process time measurement (+ JSON 500 fallback with request_id)
3. In-memory sliding-window Rate Limiting per IP
4. GZip that skips Server-Sent Event streams
5. Registration helper wiring these together with CORS and TrustedHost
"""
import re
import time
import uuid
from collections import defaultdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import ALLOWED_HOSTS, CORS_ORIGINS, RATE_LIMIT_PER_MINUTE
from app.core.logging import get_logger, request_id_ctx

logger = get_logger("app.access")

# Accept caller-supplied IDs only if they are short and log-safe (prevents log injection)
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")


def _client_ip(scope: Scope) -> str:
    client = scope.get("client")
    return client[0] if client else "unknown"


class RequestIDMiddleware:
    """
    Extracts or generates an X-Request-ID (UUID).
    Stores it in contextvars so all logging across services and routes is correlated.
    Attaches X-Request-ID to the outgoing response headers.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id")
        req_id = incoming if incoming and _VALID_REQUEST_ID.fullmatch(incoming) else str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = req_id
        token = request_id_ctx.set(req_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("X-Request-ID", req_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_ctx.reset(token)


class AccessLogMiddleware:
    """
    Measures request latency, sets the X-Process-Time header (time to first byte) and emits
    one structured access-log entry per request (total duration, incl. streamed bodies).
    Unhandled exceptions are logged and turned into a JSON 500 that carries the request_id.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        state = {"status": 500, "started": False}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                state["started"] = True
                ttfb_ms = round((time.perf_counter() - start) * 1000, 2)
                MutableHeaders(scope=message).append("X-Process-Time", f"{ttfb_ms}ms")
            await send(message)

        headers = Headers(scope=scope)
        log_extra = {
            "method": scope["method"],
            "path": scope["path"],
            "query": scope.get("query_string", b"").decode("latin-1") or None,
            "client_ip": _client_ip(scope),
            "user_agent": headers.get("user-agent", "-"),
        }

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                f"Unhandled error during HTTP {scope['method']} {scope['path']} ({duration_ms}ms)",
                extra={**log_extra, "status_code": 500, "process_time_ms": duration_ms},
            )
            if state["started"]:
                raise  # Too late to send a clean error response
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id_ctx.get()},
            )
            await response(scope, receive, send_wrapper)
            return

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        status_code = state["status"]
        log = logger.error if status_code >= 500 else logger.warning if status_code >= 400 else logger.info
        log(
            f"HTTP {scope['method']} {scope['path']} - {status_code} ({duration_ms}ms)",
            extra={**log_extra, "status_code": status_code, "process_time_ms": duration_ms},
        )


class RateLimitingMiddleware:
    """
    Sliding-window in-memory rate limiter per client IP.
    Protects login endpoints and flash-sale checkout from request flooding.
    Bypasses documentation endpoints (/docs, /redoc, /openapi.json).

    NOTE: state is per-process. With multiple workers/instances use a shared store (Redis).
    Behind a reverse proxy, run uvicorn with --proxy-headers so client IPs are real.
    """

    # Endpoints exempt from rate limits
    EXEMPT_PATHS = {"/docs", "/redoc", "/openapi.json", "/favicon.ico"}

    def __init__(self, app: ASGIApp, max_requests: int = 60, window_seconds: int = 60):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup_stale_ips(self, now: float) -> None:
        """Periodically cleans up stale client records to prevent memory growth."""
        if len(self.requests) > 5000:
            stale = [ip for ip, ts in self.requests.items() if not ts or now - ts[-1] >= self.window_seconds]
            for ip in stale:
                self.requests.pop(ip, None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self.EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        client_ip = _client_ip(scope)
        now = time.time()
        window_start = now - self.window_seconds
        timestamps = [t for t in self.requests[client_ip] if t > window_start]

        if len(timestamps) >= self.max_requests:
            self.requests[client_ip] = timestamps
            retry_after = max(1, int(self.window_seconds - (now - timestamps[0])))
            logger.warning(
                f"Rate limit exceeded for IP {client_ip} on {scope['method']} {scope['path']}",
                extra={"client_ip": client_ip, "path": scope["path"], "retry_after": retry_after},
            )
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down and try again later."},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )
            await response(scope, receive, send)
            return

        timestamps.append(now)
        self.requests[client_ip] = timestamps
        self._cleanup_stale_ips(now)
        remaining = str(max(0, self.max_requests - len(timestamps)))

        async def send_with_limits(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-RateLimit-Limit", str(self.max_requests))
                headers.append("X-RateLimit-Remaining", remaining)
            await send(message)

        await self.app(scope, receive, send_with_limits)


class SelectiveGZipMiddleware:
    """
    GZip compression that bypasses Server-Sent Event streams. Starlette's GZipMiddleware
    (0.38) buffers small streamed chunks inside zlib, which stalls 1-second SSE updates.
    """

    STREAM_SUFFIX = "/stream"

    def __init__(self, app: ASGIApp, minimum_size: int = 1000):
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].endswith(self.STREAM_SUFFIX):
            await self.app(scope, receive, send)
        else:
            await self.gzip(scope, receive, send)


def register_middlewares(app: FastAPI) -> None:
    """
    Registers all 6 middlewares. Starlette runs the LAST added middleware FIRST, so they are
    added innermost -> outermost below.

    Execution order on incoming request (outermost to innermost):
    1. TrustedHostMiddleware (Host header validation)
    2. CORSMiddleware (Preflight OPTIONS & Access-Control headers)
    3. RequestIDMiddleware (Extracts/generates X-Request-ID & sets contextvar)
    4. AccessLogMiddleware (Latency timer, structured access log, JSON 500 fallback)
    5. RateLimitingMiddleware (IP-based abuse prevention; 429s are logged with request_id)
    6. SelectiveGZipMiddleware (Response compression, skips SSE streams)
    """
    # 6. GZip (innermost - compresses responses > 1000 bytes, never SSE)
    app.add_middleware(SelectiveGZipMiddleware, minimum_size=1000)

    # 5. Rate Limiting
    app.add_middleware(RateLimitingMiddleware, max_requests=RATE_LIMIT_PER_MINUTE, window_seconds=60)

    # 4. Access logging & process time
    app.add_middleware(AccessLogMiddleware)

    # 3. Request ID
    app.add_middleware(RequestIDMiddleware)

    # 2. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        # Browsers reject credentials with a wildcard origin, so only enable them for explicit origins
        allow_credentials="*" not in CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    # 1. Trusted Host (outermost - validates HTTP Host header)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
