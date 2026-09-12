# syntax=docker/dockerfile:1

# ---------------------------------------------------------------
# Lean AI Gateway — single-container production image
# ---------------------------------------------------------------
# Serves both the Python/FastAPI backend and the compiled Vue
# admin console from a single Uvicorn process.
#
# Layer strategy (bottom → top, least-changed → most-changed):
#   1. Python venv       — only rebuilt when pyproject.toml / uv.lock change
#   2. Metadata + DB migrations + scripts — change rarely
#   3. Compiled frontend — rebuilt only when any frontend source changes
#   4. Backend source    — rebuilt most often (top layer)
#
# Because each layer is a separate Docker layer, a `docker pull`
# after a source-only change downloads just the one affected layer
# instead of the whole image.
# ---------------------------------------------------------------


# ---------- Stage 1: compile the Vue admin console ----------
FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS frontend-builder

WORKDIR /frontend

# Dependency layer — only re-installed when package.json / lockfile change.
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

# Source layer — re-built whenever any frontend file changes.
COPY frontend/ ./
RUN npm run build


# ---------- Stage 2: install Python runtime dependencies ----------
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.30@sha256:93b61e21202b1dab861092748e46bbd6e0e41dd84f59b9174efd2353186e1b47 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    TIKTOKEN_CACHE_DIR=/app/tiktoken-cache

WORKDIR /app

# Dependency layer — only re-installed when pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project \
    && /app/.venv/bin/python -c 'import tiktoken; tiktoken.get_encoding("cl100k_base")'


# ---------- Stage 3: slim runtime image ----------
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TIKTOKEN_CACHE_DIR=/app/tiktoken-cache \
    GATEWAY_ENVIRONMENT=production

# Non-root runtime user.
RUN groupadd --system gateway \
    && useradd --system --gid gateway --home-dir /app --shell /usr/sbin/nologin gateway

WORKDIR /app

# --- Layers ordered least-frequently-changing → most-frequently-changing ---

# 1) Python virtualenv (invalidated only by pyproject.toml / uv.lock changes).
COPY --from=builder --chown=gateway:gateway /app/.venv ./.venv
COPY --from=builder --chown=gateway:gateway /app/tiktoken-cache ./tiktoken-cache

# 2) Project metadata, DB migrations and helper scripts (rarely change).
COPY --chown=gateway:gateway alembic.ini pyproject.toml ./
COPY --chown=gateway:gateway migrations ./migrations
COPY --chown=gateway:gateway scripts ./scripts

# 3) Compiled Vue admin console (invalidated by any frontend/ change).
COPY --from=frontend-builder --chown=gateway:gateway /frontend/dist ./frontend/dist

# 4) Backend source code — top layer, invalidated on every backend change.
#    Keeping this last means a backend-only edit rebuilds / re-pulls only
#    this single layer.
COPY --chown=gateway:gateway src ./src

USER gateway

EXPOSE 8000

CMD ["uvicorn", "ai_gateway.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
