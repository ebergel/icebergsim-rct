# syntax=docker/dockerfile:1
# ============================================================
# Stage 1 — build the React SPA (web/dist)
# ============================================================
FROM node:22-alpine AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build
# emits /app/web/dist  (package.json: tsc -b && vite build)

# ============================================================
# Stage 2 — Python runtime (uv-managed, mirrors the repo layout)
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Dependency layer first — cached until pyproject.toml / uv.lock change
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --extra server --no-dev --no-install-project

# Project code. The layout MUST mirror the repo: main.py resolves
# web/dist and spec/examples relative to the repo root, and uv's
# editable install keeps __file__ pointing here (verified).
COPY src/ src/
COPY server/ server/
COPY spec/ spec/
RUN uv sync --frozen --extra server --no-dev

# The built SPA, exactly where DEFAULT_STATIC_DIR expects it
COPY --from=web /app/web/dist web/dist

EXPOSE 8000
# Shell-form CMD so Railway's injected $PORT expands (exec form does not).
# Bypasses main.run()'s hardcoded 127.0.0.1:8000 via uvicorn's app factory,
# without modifying the repo's localhost-only default (SPEC §20).
CMD uv run --no-sync uvicorn icebergsim_server.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}
