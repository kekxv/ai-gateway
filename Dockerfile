# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.30 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system gateway \
    && useradd --system --gid gateway --home-dir /app --shell /usr/sbin/nologin gateway

WORKDIR /app

COPY --from=builder --chown=gateway:gateway /app/.venv ./.venv
COPY --from=frontend-builder --chown=gateway:gateway /frontend/dist ./frontend/dist
COPY --chown=gateway:gateway src ./src
COPY --chown=gateway:gateway migrations ./migrations
COPY --chown=gateway:gateway scripts ./scripts
COPY --chown=gateway:gateway alembic.ini pyproject.toml ./

USER gateway

EXPOSE 8000

CMD ["uvicorn", "ai_gateway.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
