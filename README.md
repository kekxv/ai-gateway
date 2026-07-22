# Lean AI Gateway

Lean AI Gateway is a focused, multi-provider AI gateway for OpenAI, Claude, and Gemini
HTTP/SSE protocols plus OpenAI Realtime and Gemini Live WebSockets. It provides model aliases,
weighted routes, API-key scoping, MySQL-backed route health, exact `Decimal` billing, and
GZIP-compressed redacted audit logs without Redis, Celery, or Kafka.

The service is deliberately stateless outside MySQL. Run one Uvicorn process per container and
scale containers horizontally.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose v2
- MySQL 8.4 (the provided Compose service is the supported local setup)

## Local startup

Create a local environment file and replace the gateway secrets:

```bash
cp .env.example .env
uv run python - <<'PY'
import secrets
from cryptography.fernet import Fernet

print("GATEWAY_JWT_SECRET=" + secrets.token_urlsafe(48))
print("GATEWAY_ENCRYPTION_KEY=" + Fernet.generate_key().decode())
PY
```

Paste the generated values into `.env`. Never commit `.env`. Compose reads `MYSQL_DATABASE`,
`MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_ROOT_PASSWORD` from that file and uses the same values
for the gateway database URL. The checked-in values are local-development defaults only; replace
both MySQL passwords outside a disposable workstation. Because Compose embeds `MYSQL_PASSWORD`
in a SQLAlchemy URL, use URL-safe password characters (`A-Z`, `a-z`, `0-9`, `.`, `_`, `~`, `-`).
For local host execution, keep `GATEWAY_DATABASE_URL` aligned with those values and
`127.0.0.1:3306`.

MySQL is published only on `127.0.0.1:3306`; it is not exposed on external host interfaces.
`compose.yaml` is the canonical and only Compose file.

Start MySQL, install the frozen dependency set, and migrate before starting the app:

```bash
docker compose up -d mysql
uv sync --frozen
uv run alembic upgrade head
uv run python scripts/create_admin.py --email admin@example.com
uv run uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8000 --reload
```

Check readiness:

```bash
curl --fail http://127.0.0.1:8000/health
```

`/health` returns `200 {"status":"ok"}` only when MySQL is reachable. Startup also refuses a
database that is not at migration head `0004`.

## Docker deployment

For container deployment, set `GATEWAY_ENVIRONMENT=production` in `.env`, use non-example JWT,
Fernet, and MySQL secrets, and leave the database hostname to the `compose.yaml` override
(`mysql`). Then:

```bash
docker compose build gateway
docker compose up -d mysql
docker compose run --rm gateway alembic upgrade head
docker compose run --rm gateway python scripts/create_admin.py --email admin@example.com
docker compose up -d gateway
docker compose ps
```

The runtime container runs as the non-root `gateway` user. Compose makes its root filesystem
read-only, mounts `/tmp` as tmpfs, drops every Linux capability, and enables
`no-new-privileges`.

For non-interactive bootstrap, inject a short-lived environment variable and remove it
immediately afterward:

```bash
export GATEWAY_BOOTSTRAP_PASSWORD='replace-this-in-your-shell'
docker compose run --rm \
  -e GATEWAY_BOOTSTRAP_PASSWORD \
  gateway python scripts/create_admin.py \
  --email admin@example.com \
  --password-env GATEWAY_BOOTSTRAP_PASSWORD
unset GATEWAY_BOOTSTRAP_PASSWORD
```

## Obtain a gateway API key

Login as the administrator, then use the admin APIs to create a user, provider, model, alias,
route, API key, and balance adjustment. The interactive API schema at `/docs` lists every field.
Only the API-key create or rotate response contains the raw key; store it immediately.

```bash
export GATEWAY_URL=http://127.0.0.1:8000
export ADMIN_TOKEN="$({
  curl --silent --fail "$GATEWAY_URL/auth/login" \
    -H 'content-type: application/json' \
    -d '{"email":"admin@example.com","password":"replace-me"}'
} | uv run python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
```

The examples below assume provisioning is complete:

```bash
export GATEWAY_API_KEY='sk-gw-replace-me'
export MODEL_ALIAS='friendly-chat'
```

Aliases are accepted inbound and rewritten to the selected `ModelRoute.upstream_model` before
the provider request or WebSocket handshake.

## OpenAI-compatible HTTP and SSE

Non-streaming:

```bash
curl --fail "$GATEWAY_URL/v1/chat/completions" \
  -H "Authorization: Bearer $GATEWAY_API_KEY" \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL_ALIAS\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}],\"max_tokens\":128}"
```

Streaming:

```bash
curl --no-buffer --fail "$GATEWAY_URL/v1/chat/completions" \
  -H "Authorization: Bearer $GATEWAY_API_KEY" \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL_ALIAS\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}],\"max_tokens\":128,\"stream\":true}"
```

## Claude-compatible HTTP and SSE

Non-streaming:

```bash
curl --fail "$GATEWAY_URL/v1/messages" \
  -H "x-api-key: $GATEWAY_API_KEY" \
  -H 'anthropic-version: 2023-06-01' \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL_ALIAS\",\"max_tokens\":128,\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

Streaming:

```bash
curl --no-buffer --fail "$GATEWAY_URL/v1/messages" \
  -H "x-api-key: $GATEWAY_API_KEY" \
  -H 'anthropic-version: 2023-06-01' \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL_ALIAS\",\"max_tokens\":128,\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

## Gemini-compatible HTTP and SSE

Non-streaming:

```bash
curl --fail "$GATEWAY_URL/v1beta/models/$MODEL_ALIAS:generateContent" \
  -H "x-goog-api-key: $GATEWAY_API_KEY" \
  -H 'content-type: application/json' \
  -d '{"contents":[{"role":"user","parts":[{"text":"Hello"}]}],"generationConfig":{"maxOutputTokens":128}}'
```

Streaming:

```bash
curl --no-buffer --fail \
  "$GATEWAY_URL/v1beta/models/$MODEL_ALIAS:streamGenerateContent?alt=sse" \
  -H "x-goog-api-key: $GATEWAY_API_KEY" \
  -H 'content-type: application/json' \
  -d '{"contents":[{"role":"user","parts":[{"text":"Hello"}]}],"generationConfig":{"maxOutputTokens":128}}'
```

## OpenAI Realtime WebSocket

Using `websocat`:

```bash
websocat \
  -H="Authorization: Bearer $GATEWAY_API_KEY" \
  -H='Sec-WebSocket-Protocol: realtime' \
  "ws://127.0.0.1:8000/v1/realtime?model=$MODEL_ALIAS"
```

Then send a frame such as:

```json
{"type":"session.update","session":{"model":"friendly-chat","modalities":["text"]}}
```

## Gemini Live WebSocket

```bash
websocat \
  -H="x-goog-api-key: $GATEWAY_API_KEY" \
  -H='Sec-WebSocket-Protocol: gemini-live' \
  ws://127.0.0.1:8000/v1beta/live
```

The first frame must identify the model when it is not in the query string:

```json
{"setup":{"model":"models/friendly-chat","generationConfig":{"responseModalities":["TEXT"]}}}
```

WebSockets are transparent same-protocol relays: text/binary frames, ping/pong, and close details
are propagated; client credentials are removed and provider credentials are injected upstream.

## Quality gates

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway' \
  uv run pytest -W error --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90
docker build -t lean-ai-gateway:test .
docker compose config --quiet
```

The E2E suite uses only MySQL and loopback fake providers; it never requires real provider
credentials or public network access.

## Further documentation

- [Architecture](docs/architecture.md)
- [Protocol compatibility](docs/protocol-compatibility.md)
- [Operations runbook](docs/operations.md)
