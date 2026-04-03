# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: Build Go backend
FROM golang:1.22-alpine AS backend-builder

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache gcc musl-dev sqlite-dev

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Copy frontend build output for go:embed
COPY --from=frontend-builder /app/web/dist ./web/dist

# Build binary
RUN CGO_ENABLED=1 GOOS=linux CGO_CFLAGS="-D_LARGEFILE64_SOURCE" go build -a -installsuffix cgo -o ai-gateway ./cmd/server

# Stage 3: Runtime
FROM alpine:3.19

# Install runtime dependencies
RUN apk add --no-cache sqlite-libs ca-certificates

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