# Architecture

## Deployment model

Each gateway container runs one Uvicorn process. Request state, routing health, model-sync
coordination, balances, and audit history live in MySQL 8.4, so replicas do not need shared
in-memory state or an external queue/cache. Add replicas behind a load balancer; do not run
multiple workers inside one container.

The main components are:

- FastAPI routers for admin/auth, three HTTP/SSE protocols, model listing, and two WebSocket
  endpoints.
- Protocol adapters that translate through canonical request, response, usage, and stream-event
  types.
- Catalog and routing services that resolve aliases, enforce API-key scope, select weighted
  healthy routes, and rewrite the inbound name to `ModelRoute.upstream_model`.
- Long-lived proxy-aware HTTP clients and transparent WebSocket relay transport.
- Billing and audit services that use independent MySQL transactions so cleanup can complete even
  after a client disconnect or upstream failure.

No Redis, Celery, Kafka, or process-local coordination is required.

## HTTP/SSE request sequence

```mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway router
    participant DB as MySQL
    participant P as Provider

    C->>G: Native request + gateway API key
    G->>DB: Authenticate key; update last_used_at
    G->>DB: Resolve canonical model/alias
    G->>G: Decode inbound protocol to canonical form
    G->>DB: Lock account; reserve worst-case balance
    G->>DB: Insert STARTED request log (redacted GZIP)
    G->>DB: Select weighted, scoped, healthy route
    G->>G: Rewrite alias to upstream_model; convert protocol
    G->>P: Provider-authenticated HTTP/SSE request
    P-->>G: Native response or stream
    G->>DB: Record route success/failure atomically
    G->>G: Convert response/stream to inbound protocol
    G->>DB: Lock account; release reservation and charge usage
    G->>DB: Complete/fail audit log in isolated transaction
    G-->>C: Native response/SSE or sanitized error
```

For SSE, the gateway prefetches the first provider event before committing a successful downstream
response. Stream finalization is shielded from cancellation so billing release/charge and audit
completion are attempted when the client disconnects.

## WebSocket request sequence

1. Authenticate the gateway API key before accepting an upstream connection.
2. Accept the client socket and resolve the model from the query string or first setup frame.
3. Select a route with the same protocol and a non-null `websocket_url`.
4. Reserve balance and write the initial redacted audit record.
5. Rewrite the query/setup model to `upstream_model`; remove client credentials and inject provider
   credentials.
6. Relay text/binary frames bidirectionally. Observe native usage frames when available and use
   bounded estimates otherwise.
7. Checkpoint long sessions by token threshold/time, then settle the final reservation and request
   log when either peer closes.

OpenAI Realtime and Gemini Live are same-protocol transparent relays. They are not converted into
each other.

## Schema ownership

| Tables | Owner | Purpose |
|---|---|---|
| `users` | auth/admin | Password hash, role, active state, encrypted active/pending TOTP secret |
| `api_keys`, `api_key_providers`, `api_key_models` | auth/admin | Hashed gateway keys and provider/model scope joins |
| `providers`, `provider_protocols` | catalog/admin | Encrypted provider credentials/headers, HTTP and WebSocket endpoints |
| `models`, `model_aliases`, `model_routes` | catalog/routing | Canonical models, inbound aliases, prices, route weights, upstream names, health state |
| `accounts`, `ledger_entries` | billing | Eight-decimal balances, total spend, immutable reservation/release/usage/adjustment entries |
| `request_logs` | audit | Request outcome, usage/cost, route IDs, and redacted GZIP request/response detail |
| `alembic_version` | migrations | Exact schema revision required by application startup |

Provider API secrets and extra headers are Fernet ciphertext. Gateway API keys are stored only as
SHA-256 digests plus a short lookup prefix. Money is `DECIMAL(20,8)` and application arithmetic
uses Python `Decimal` with one final eight-decimal rounding step.

## Transaction and locking boundaries

There is intentionally no transaction spanning a provider network call.

| Operation | Boundary and concurrency control |
|---|---|
| Admin user/provider/model/route CRUD | One request transaction, committed only after validation and flush |
| API-key authentication | Request session transaction updates `last_used_at`; key digest comparison is constant-time |
| API-key rotation | Locks the existing key row, disables it, clones scope joins, and inserts the replacement in one transaction |
| TOTP setup/confirm | Locks the user row with `SELECT ... FOR UPDATE` before replacing encrypted pending/active secrets |
| Initial balance reservation | Dedicated mutation session; locks the account row and inserts an idempotent reservation entry |
| Settlement | Dedicated mutation session; locks account and reservation; inserts matching release and usage entries atomically |
| Manual balance adjustment | Dedicated mutation session; locks account and idempotency key before mutation |
| Orphan recovery | Claims an expired reservation under row lock/version token, then performs normal idempotent settlement |
| Request audit start/finish | Separate short transactions; audit write failure is logged without exposing bodies or credentials |
| Route success/failure | Separate atomic `UPDATE`; failure count/open timestamp transitions are database expressions |
| Half-open claim | Conditional atomic update lets only one replica claim an expired open route |
| Scheduled model sync | MySQL `GET_LOCK('model-sync:<provider_id>', 0)` elects one replica; catalog changes commit together |

These boundaries let a replica fail between stages without holding database locks across slow
provider I/O. Idempotency keys and the recovery scheduler reconcile abandoned reservations.

## Route health

Weighted selection considers only enabled models, providers, provider protocols, routes, API-key
scope, requested transport, and eligible runtime state. Penalizing failures include selected
timeouts, 408/429/5xx responses, DNS/TLS errors, and defined WebSocket network/close errors.

After the configured threshold, the route becomes `open` until `disabled_until`. Exactly one
replica can claim it as `half_open`; a success closes and resets it, while another penalizing
failure reopens it. Client validation errors and most provider 4xx responses do not poison health.

## Trust and secret boundaries

- Inbound gateway credentials are never forwarded upstream.
- Provider credentials and configured provider headers are decrypted only while constructing an
  outbound request/handshake.
- Structured error handlers omit request bodies and secret values.
- Audit headers remove authorization/API-key/cookie fields; JSON keys such as `password`,
  `secret`, `credential`, and `api_key` become `[REDACTED]` before GZIP compression.
- Proxy credentials are configuration secrets and must not be placed in log messages or docs.
