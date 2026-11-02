# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# QuickKart backend (FastAPI + SQLAlchemy async + asyncpg)
# Multi-stage: build wheels in a throwaway stage, ship a slim non-root runtime.
# ---------------------------------------------------------------------------

# ---------- Stage 1: build Python wheels ----------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# build-essential only lives in this stage (needed if a wheel must compile from source)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt


# ---------- Stage 2: runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Install dependencies from prebuilt wheels (no compiler in the final image)
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/* \
    && rm -rf /wheels

# Unprivileged user
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY --chown=app:app app ./app

USER app

EXPOSE 8000

# /health checks the DB connection too, so "healthy" means the API can actually serve traffic
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=4).status == 200 else 1)"

# IMPORTANT: keep a single worker. Live delivery tracking (1-Hz GPS state), the rate limiter and
# the order-expiry sweeper keep state in process memory. Scale horizontally only after moving
# that state to Redis.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]

