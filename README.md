# Lean AI Gateway

**[English](README.md)** | **[中文](README.zh-CN.md)**

Lean AI Gateway is a focused, multi-provider AI gateway for OpenAI, Claude, and Gemini
HTTP/SSE protocols plus OpenAI Realtime and Gemini Live WebSockets. It provides model aliases,
weighted routes, API-key scoping, MySQL-backed route health, exact `Decimal` billing, and
GZIP-compressed redacted audit logs without Redis, Celery, or Kafka.

The service is deliberately stateless outside MySQL. Run one Uvicorn process per container and
scale containers horizontally.

## Features

- OpenAI, Claude, and Gemini compatible HTTP APIs, including streaming SSE responses.
- OpenAI Realtime and Gemini Live WebSocket relays.
- Automatic conversion among OpenAI, Claude, and Gemini request/response protocols. Native OpenAI
  Responses is passed through by default; operation-specific exceptions are documented below.
- Weighted-random routing with MySQL-backed health state, cooldowns, half-open probes, and
  automatic failover away from unhealthy routes.
- Providers with multiple protocols, optional model discovery, HTTP/HTTPS proxy support, and
  `NO_PROXY` rules for hosts, ports, IPv4/IPv6 addresses, and CIDR ranges.
- Canonical models, aliases, exact per-million-token pricing, and provider-specific
  `upstream_model` rewriting. Aliases are returned by model discovery but are never forwarded
  upstream as provider model names.
- Independently managed API keys scoped to all resources, selected providers, selected models,
  or both provider and model sets.
- Public registration with an exactly-once first administrator, JWT access/refresh
  authentication, role-based authorization, password changes, and TOTP enrollment,
  replacement, or disable.
- Regular-user console access to the enabled model catalog and self-service API keys; ownership is
  derived from the authenticated account and provider-scoped keys remain administrator-only.
- Exact `Decimal` balance accounting, reservations, settlement, adjustments, and an immutable
  ledger.
- Redacted request logs with cursor pagination and GZIP-compressed request/response details.
- Support for provider and model-level price multipliers for flexible billing adjustments.
- A Chinese Vue 3 administration console for day-to-day gateway operations.
- Administrator catalog backup/import controls and a legacy SQLite migration path.

## Supported interfaces

| Interface | Endpoint | Modes |
| --- | --- | --- |
| OpenAI chat completions | `/v1/chat/completions` | HTTP, SSE |
| OpenAI Responses API | `/v1/responses` | HTTP, SSE |
| OpenAI embeddings | `/v1/embeddings` | HTTP |
| OpenAI completions (Legacy) | `/v1/completions` | HTTP |
| OpenAI model catalog | `/v1/models`, `/v1/models/{model}` | HTTP |
| OpenAI Realtime | `/v1/realtime` | WebSocket |
| Claude messages | `/anthropic/v1/messages` (recommended), `/v1/messages` (legacy alias) | HTTP, SSE |
| Claude model catalog | `/anthropic/v1/models`, `/anthropic/v1/models/{model}`; legacy `/v1/models` uses `anthropic-version` | HTTP |
| Gemini generate content | `/v1beta/models/{model}:generateContent` | HTTP |
| Gemini stream generate content | `/v1beta/models/{model}:streamGenerateContent` | SSE |
| Gemini model catalog | `/v1beta/models` | HTTP |
| Gemini Live | `/v1beta/live` | WebSocket |
| Administration console | `/console/` | Browser SPA |
| OpenAPI documentation | `/docs`, `/redoc`, `/openapi.json` | HTTP |

For detailed information about the OpenAI API endpoints, see the [OpenAI API Reference](docs/openai-api-reference.md).

### OpenAI API Compatibility

The gateway supports multiple OpenAI API formats for compatibility with various CLI tools and applications:

- **Chat Completions API** (`/v1/chat/completions`): The standard chat completions endpoint
- **Responses API** (`/v1/responses`): Native OpenAI Responses pass-through by default, with portable conversion for Claude, Gemini, or explicitly incompatible OpenAI backends.
- **Embeddings API** (`/v1/embeddings`): Generate text embeddings for RAG and vector operations
- **Completions API** (`/v1/completions`): Legacy text completions endpoint for backward compatibility

The Responses API accepts both formats:
```json
// Simple string input
{"model": "gpt-4", "input": "Hello, how are you?"}

// Structured conversation history
{"model": "gpt-4", "input": [{"role": "user", "content": "Hello"}]}
```

OpenAI provider protocols default to native Responses support. Set `supports_responses=false` only
for OpenAI-compatible backends that expose Chat Completions but not Responses; this enables the
portable Responses-to-Chat fallback. Native Responses fields are otherwise forwarded to
`/v1/responses`. Embeddings and Legacy Completions require an OpenAI route and are forwarded to
`/v1/embeddings` and `/v1/completions` respectively; they are never converted to Chat, Claude, or
Gemini. See [protocol compatibility](docs/protocol-compatibility.md) for portable feature limits.


## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose v2
- MySQL 8.4 (the provided Compose service is the supported local setup)
- Node.js 22 and npm (only for console development and frontend tests)

## One-command Docker example

For a disposable local evaluation, the [`example/`](example/) directory builds the gateway,
starts MySQL, applies migrations, and serves the console without built-in account credentials:

```bash
cd example
docker compose up
```

Open <http://127.0.0.1:8000/console/register> and register the first account, which becomes the
administrator. Later registrations are regular users. Public registration is enabled by default;
an administrator can close or reopen it from **Security settings → Public registration**. Closing
it hides the registration form and makes the registration API reject new accounts. See the
[example README](example/README.md) for the initialization flow and cleanup.

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
both MySQL passwords before the first `docker compose up` that initializes a non-disposable
volume. MySQL initialization variables do not change passwords in an existing volume. To rotate
an existing deployment, authenticate with the old credential, run `ALTER USER`, then update the
environment and roll the gateway; see the operations runbook. Because Compose embeds
`MYSQL_PASSWORD` in a SQLAlchemy URL, use URL-safe password characters (`A-Z`, `a-z`, `0-9`, `.`,
`_`, `~`, `-`). For local host execution, keep `GATEWAY_DATABASE_URL` aligned with those values
and `127.0.0.1:3306`.

MySQL is published only on `127.0.0.1:3306`; it is not exposed on external host interfaces.
The root `compose.yaml` is the canonical Compose file for normal development and deployment;
`example/compose.yaml` is a separate, disposable one-command demonstration.

Start MySQL, install the frozen dependency set, and migrate before starting the app:

```bash
docker compose up -d mysql
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8000 --reload
```

Open <http://127.0.0.1:8000/console/register> to create the first administrator. For automated
deployments, `scripts/create_admin.py` remains available as the optional non-interactive path.

Check readiness:

```bash
curl --fail http://127.0.0.1:8000/health
```

`/health` returns `200 {"status":"ok"}` only when MySQL is reachable. Startup also refuses a
database that is not at migration head `0010`.

### Admin console development

Run the backend and Vite development server in separate terminals after migrating the database.
If the database has no users, create the first administrator at `/console/register`:

```bash
# terminal 1: backend
uv run uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8000 --reload

# terminal 2: frontend dev server
npm ci --prefix frontend
npm --prefix frontend run dev
# open http://127.0.0.1:5173/console/
```

For a production-style local check, compile the console and let FastAPI serve it from the public
gateway process:

```bash
npm --prefix frontend run build
uv run uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000/console/
```

The public model gateway remains on port `8000`; the compiled console uses the same origin and
does not require a separate production Node process. Port `5173` is only the Vite development
server.

All authenticated users can browse enabled models and aliases, manage only their own API keys,
and access account security settings. Regular-user keys may cover all models or a selected enabled
model set; they cannot select providers or another owner. Administrator accounts additionally have:

- dashboard usage, cost, health, and resource summaries;
- provider protocols, credentials, model synchronization, models, aliases, and weighted routes;
- users, balances, immutable ledger entries, and global/provider-scoped API-key management;
- one-time API-key display with explicit copy/download acknowledgement;
- request-log filters, backend cursor navigation, and redacted JSON detail inspection;
- password changes plus TOTP enrollment, verified replacement, and verified disable.

TOTP setup generates a random secret by default. The Security settings page also offers an
advanced custom-secret option for migrations and managed authenticators. A custom value must be
RFC 4648 Base32, decode to at least 160 bits, and is normalized by removing spaces/hyphens and
uppercasing it. Use only a randomly generated, securely backed-up secret that is not reused:
weak or reused values can lead to account takeover, while losing the value can lock the user out.
The console shows this warning and requires explicit acknowledgement before submission. The new
secret remains encrypted and pending until a code generated from it is confirmed; an existing
active TOTP secret continues to work until that confirmation succeeds.

JWT access and refresh tokens are stored in `sessionStorage`, not `localStorage`. Provider
credentials, TOTP codes, passwords, and full API keys are never persisted or redisplayed after
their one-time workflow ends.

### Catalog backup and legacy migration

Administrators can export or merge the provider/model catalog from the Providers page. Exports are
redacted by default; the console requires an explicit warning confirmation before downloading a
backup that includes upstream credentials.

To migrate one user's channel/provider/model configuration from the legacy Go project
[`kekxv/ai-gateway`](https://github.com/kekxv/ai-gateway), export its SQLite data to the versioned
catalog bundle and import that bundle from the Providers page:

```bash
uv run python scripts/export_legacy_sqlite_catalog.py /path/to/ai-gateway.db \
  --user admin@example.com \
  --include-unowned \
  --include-secrets \
  --output legacy-user-catalog.json
```

See the [catalog backup and legacy SQLite migration guide](docs/catalog-import-export.md) for the
complete procedure, user selection, option meanings, API import example, verification steps,
secret handling, and rollback limitations.

## Docker deployment

For container deployment, set `GATEWAY_ENVIRONMENT=production` in `.env`, use non-example JWT,
Fernet, and MySQL secrets, and leave the database hostname to the `compose.yaml` override
(`mysql`). All administrator bootstrap variables may remain absent: after startup, register the
first account at `/console/register`. The first committed registration becomes administrator and
later registrations become regular users.

For automated deployments, optionally set the following values before the first start to create
the administrator non-interactively. The TOTP secret is optional and must be Base32 with at least
160 bits of decoded entropy:

```bash
uv run python -c 'import pyotp; print(pyotp.random_base32())'

# Put the generated value and the other bootstrap values in .env or a secret-backed env file:
# GATEWAY_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
# GATEWAY_BOOTSTRAP_ADMIN_PASSWORD=<strong-initial-password>
# GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET=<generated-base32-secret>

docker compose up -d --build
docker compose ps
```

The one-shot `setup` service waits for MySQL, applies all migrations, and can then create the
administrator. If all three bootstrap variables are empty it skips administrator creation and
the registration page remains the initialization path. If
any is configured, email and password are required while TOTP remains optional. Bootstrap values
only affect a newly created email: an existing administrator's password and TOTP configuration
are never overwritten, including on later deployments or concurrent setup runs. After a
successful first start, remove all three bootstrap variables (especially the password and TOTP
secret) from `.env` or the backing secret source, then remove the exited setup container with
`docker compose rm -f setup`. The long-running `gateway` service explicitly overrides all three
variables to empty values, so they are not retained in its container environment. Subsequent
Compose starts recreate setup with empty bootstrap values, migrate, and start the gateway normally.

Both the runtime container and the setup container run as the non-root `gateway` user. Compose
makes their root filesystems read-only, mounts `/tmp` as tmpfs, drops every Linux capability, and
enables `no-new-privileges`. In Kubernetes or another orchestrator, run `alembic upgrade head` and
the optional `scripts/create_admin.py` invocation in a separate serialized release job before
starting the matching gateway image.

### Published images

After the full CI quality job succeeds, pushes to the default branch and version tags publish a
multi-stage production image to GitHub Container Registry:

```bash
docker pull ghcr.io/<owner>/<repository>:latest
docker pull ghcr.io/<owner>/<repository>:<commit-sha>
docker pull ghcr.io/<owner>/<repository>:1.2.3
```

Default-branch builds publish `latest`, the branch name, and the short commit SHA. A tag such as
`v1.2.3` publishes `1.2.3`, `1.2`, `1`, and the commit SHA. Replace the placeholders with this
repository's lowercase GitHub owner and repository name.

The final image contains the Python runtime and the compiled Vue console, runs as the non-root
`gateway` user, and does not contain Node.js or npm. The image defaults to production mode, so
valid JWT, Fernet, and database secrets are required at startup.

## Important configuration

Common configuration examples and operational guidance live in [`.env.example`](.env.example)
and the [operations runbook](docs/operations.md). The most important settings are:

| Setting | Purpose |
| --- | --- |
| `GATEWAY_DATABASE_URL` | Async SQLAlchemy URL for the MySQL application database |
| `GATEWAY_JWT_SECRET` | Signs access and refresh tokens; use a unique high-entropy value |
| `GATEWAY_ENCRYPTION_KEY` | Fernet key for provider credentials, headers, and TOTP secrets |
| `GATEWAY_BOOTSTRAP_ADMIN_EMAIL` | Optional first-run administrator email; requires the password setting |
| `GATEWAY_BOOTSTRAP_ADMIN_PASSWORD` | First-run administrator password; remove after successful bootstrap |
| `GATEWAY_BOOTSTRAP_ADMIN_TOTP_SECRET` | Optional first-run Base32 TOTP secret of at least 160 bits; remove after successful bootstrap |
| `GATEWAY_HTTP_PROXY`, `GATEWAY_HTTPS_PROXY` | Optional outbound provider proxies |
| `GATEWAY_NO_PROXY` | Comma-separated host, suffix, port, IP, CIDR, or `*` bypass rules |
| `GATEWAY_AUDIT_BODY_LIMIT_BYTES` | Maximum request/response body size retained for audit detail |
| `GATEWAY_BILLING_DEFAULT_MAX_OUTPUT_TOKENS` | Reservation fallback when a request omits an output limit |

Production startup rejects the example JWT and encryption secrets. Keep all credentials in a
secret manager. The provided Compose `setup` service is its serialized release step; other
orchestrators should run the same migration/bootstrap work in a separate release job before
starting the new application version.

## Obtain a gateway API key

Register or log in as the administrator, then use the admin APIs to create a user, provider, model, alias,
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

Use the dedicated Anthropic base URL with Anthropic SDKs. The SDK appends `/v1/messages` and
other native resource paths:

```bash
export ANTHROPIC_BASE_URL="$GATEWAY_URL/anthropic"
```

`/v1/messages` remains available as a backward-compatible alias. Provider protocol rows keep
their own upstream `base_url`; this public namespace does not change upstream configuration.

Non-streaming:

```bash
curl --fail "$ANTHROPIC_BASE_URL/v1/messages" \
  -H "x-api-key: $GATEWAY_API_KEY" \
  -H 'anthropic-version: 2023-06-01' \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL_ALIAS\",\"max_tokens\":128,\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

Streaming:

```bash
curl --no-buffer --fail "$ANTHROPIC_BASE_URL/v1/messages" \
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

Tests require the dedicated `gateway_test` schema. `docker compose up -d mysql mysql-test-setup`
creates/grants it even when upgrading an existing persistent MySQL volume. The fixture refuses a
URL without `test` in the database name, refuses the application schema, and removes only gateway
tables plus `alembic_version` from that isolated schema.

```bash
docker compose up -d mysql mysql-test-setup
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src scripts
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' \
  uv run pytest -W error --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm exec --prefix frontend -- playwright install --with-deps chromium
E2E_ADMIN_EMAIL='admin@example.com' E2E_ADMIN_PASSWORD='short-lived-password' \
  npm --prefix frontend run e2e
docker build -t lean-ai-gateway:test .
docker compose config --quiet
```

Run the browser E2E suite against a freshly migrated application database with no users. Its first
test registers `E2E_ADMIN_EMAIL` with `E2E_ADMIN_PASSWORD` and verifies that the account reaches
administrator pages. The suite uses only MySQL and loopback fake providers; it never requires real
provider credentials or public network access. It creates uniquely named resources, removes
disposable resources in reverse dependency order, and disables users whose immutable ledger
history prevents deletion.

## Further documentation

- [Architecture](docs/architecture.md)
- [Protocol compatibility](docs/protocol-compatibility.md)
- [Operations runbook](docs/operations.md)
- Runtime API reference: `/docs` or `/redoc`
