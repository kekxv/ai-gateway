# syntax=docker/dockerfile:1.4

# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/web

# Copy package files first for better caching
COPY web/package*.json ./

# Use BuildKit cache for npm packages
RUN --mount=type=cache,target=/root/.npm \
    npm ci

# Copy source and build
COPY web/ ./
RUN npm run build

# Stage 2: Build Go backend
FROM golang:1.25-alpine AS backend-builder

WORKDIR /app

# Copy go mod files first for better caching
COPY go.mod go.sum ./

# Use BuildKit cache for Go modules
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

# Copy source code
COPY . .

# Copy frontend build output for go:embed
COPY --from=frontend-builder /app/web/dist ./web/dist

# Build binary with optimizations
RUN --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux go build -a -ldflags='-s -w' -o ai-gateway ./cmd/server

# Stage 3: Runtime
FROM alpine:3.19

# Install runtime dependencies
RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

# Copy binary and config
COPY --from=backend-builder /app/ai-gateway .
COPY --from=backend-builder /app/configs ./configs

# Environment variables
ENV DATABASE_URL="file:/app/ai-gateway.db"
ENV JWT_SECRET=""
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV NO_PROXY=""

EXPOSE 3000

CMD ["./ai-gateway"]