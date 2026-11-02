# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# QuickKart frontend (React 19 + TanStack Start + Vite 8 + Tailwind v4)
#
# Targets:
#   runtime (default) - production SSR server built by Nitro with the `node-server` preset
#   dev               - Vite dev server with hot reload (used by docker-compose.dev.yml)
# ---------------------------------------------------------------------------

ARG NODE_VERSION=22

# ---------- Stage 1: install dependencies (reproducible, from bun.lock) ----------
FROM node:${NODE_VERSION}-bookworm-slim AS deps
WORKDIR /app

# The repo ships a bun.lock (no package-lock.json), so install with bun for a reproducible tree
RUN npm install -g bun@1 && npm cache clean --force

COPY package.json bun.lock bunfig.toml ./
RUN bun install --frozen-lockfile || (echo "bun.lock is out of date, resolving fresh" && bun install)


# ---------- Stage 2: dev server (hot reload) ----------
FROM deps AS dev
ENV NODE_ENV=development
COPY . .
EXPOSE 8080
CMD ["npx", "vite", "dev", "--host", "0.0.0.0", "--port", "8080"]


# ---------- Stage 3: production build ----------
FROM deps AS build

# URL the *browser* uses to reach the FastAPI backend (baked into the client bundle)
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    NODE_ENV=production \
    # @lovable.dev/vite-tanstack-config defaults Nitro to `cloudflare-module`; NITRO_PRESET overrides it
    # outside the Lovable sandbox, producing a self-contained Node server in .output/
    NITRO_PRESET=node-server

COPY . .
RUN npm run build \
    && test -f .output/server/index.mjs \
    || (echo "ERROR: Nitro did not emit .output/server/index.mjs (check NITRO_PRESET=node-server)" && exit 1)


# ---------- Stage 4: runtime ----------
FROM node:${NODE_VERSION}-bookworm-slim AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000

# Nitro bundles all server dependencies into .output, so node_modules is not needed at runtime
COPY --from=build --chown=node:node /app/.output ./.output

USER node
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
    CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"

CMD ["node", ".output/server/index.mjs"]

