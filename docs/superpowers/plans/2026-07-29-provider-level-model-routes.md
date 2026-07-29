# Provider-Level Model Routes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make model routes target providers, prefer a provider's protocol matching the inbound request for transparent forwarding, and allow administrators to delete routes while retaining detached request history.

**Architecture:** `ModelRoute` becomes the weighted model-to-provider edge and no longer stores a provider-protocol foreign key. The router expands each eligible provider route over that provider's enabled protocol configurations, chooses one protocol per route with an exact inbound-protocol match first, and applies weights once per provider route. Route deletion nulls historical `RequestLog.model_route_id` references before deleting the route.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic/MySQL, pytest, Vue 3, TypeScript, Vitest.

## Global Constraints

- Preserve the existing uncommitted Claude protocol conversion changes.
- Upgrade duplicate routes by retaining the smallest route ID for each `(model_id, provider_id)` and repointing request logs to it.
- A provider route must reference an existing provider with at least one configured protocol; disabled protocols remain ineligible at runtime.
- Prefer exact inbound protocol for HTTP; fall back to cross-protocol conversion only when no remaining exact-protocol route is available.
- WebSocket routing continues to require the inbound protocol and WebSocket capability.
- Route deletion retains request logs and clears only their `model_route_id`.

---

### Task 1: Provider-Level Database and API Contract

**Files:**
- Create: `migrations/versions/0013_provider_level_model_routes.py`
- Modify: `src/ai_gateway/db/models/catalog.py`
- Modify: `src/ai_gateway/catalog/schemas.py`
- Modify: `src/ai_gateway/admin/models.py`
- Test: `tests/integration/test_schema.py`
- Test: `tests/integration/admin/test_catalog.py`
- Test: `tests/unit/migrations/test_0013_provider_level_model_routes.py`

**Interfaces:**
- `ModelRouteCreate(model_id, provider_id, upstream_model, weight, enabled)` contains no `provider_protocol_id`.
- `ModelRouteResponse` contains no `provider_protocol_id`.
- Database uniqueness is `uq_model_routes_model_provider(model_id, provider_id)`.

- [ ] **Step 1: Write failing schema and admin API tests**

  Assert that `model_routes` has no `provider_protocol_id`, create/update payloads accept only `provider_id`, duplicate model/provider routes return `model_route_conflict`, and a provider without any protocol returns `invalid_route_reference`.

- [ ] **Step 2: Run the focused tests and verify RED**

  Run: `GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/test_schema.py tests/integration/admin/test_catalog.py -q`

  Expected: failures mention the old `provider_protocol_id` column and required payload field.

- [ ] **Step 3: Add migration and update ORM/API models**

  Migration upgrade must create a temporary mapping from every duplicate route ID to `MIN(id)`, update `request_logs.model_route_id`, delete non-retained routes, drop the protocol foreign key/column and old unique constraint, then add `uq_model_routes_model_provider`. Downgrade restores `provider_protocol_id` using each provider's minimum protocol ID.

  Update route validation to query an enabled `ProviderProtocol` by `provider_id` rather than accept a protocol ID.

- [ ] **Step 4: Run focused tests and verify GREEN**

  Run the Task 1 command and the migration unit test.

### Task 2: Native-Protocol-First Route Selection

**Files:**
- Modify: `src/ai_gateway/routing/service.py`
- Modify: `src/ai_gateway/gateway/service.py`
- Modify: `src/ai_gateway/routing/types.py`
- Test: `tests/unit/routing/test_weighted.py`
- Test: `tests/unit/routing/test_candidate_projection.py`
- Test: `tests/contract/gateway/test_non_streaming.py`

**Interfaces:**
- `Router.select_route(..., required_protocol=None, *, preferred_protocol=None, ...)` accepts the inbound protocol separately from hard transport requirements.
- `GatewayService` passes `prepared.inbound_protocol` as `preferred_protocol`.
- `RouteCandidate` still contains the selected runtime `provider_protocol_id` and protocol connection details.

- [ ] **Step 1: Write failing routing tests**

  Create equal-weight provider routes where only one provider supports Claude and assert a Claude inbound preference always chooses that route before OpenAI conversion. Create one provider with both OpenAI and Claude protocols and assert its Claude protocol configuration is projected into the candidate. Exclude the native route and assert selection falls back to a convertible route.

- [ ] **Step 2: Run focused tests and verify RED**

  Run: `GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/unit/routing/test_weighted.py tests/unit/routing/test_candidate_projection.py tests/contract/gateway/test_non_streaming.py -q`

- [ ] **Step 3: Implement provider grouping and protocol preference**

  Query all enabled protocol rows for each eligible provider route, group rows by `route_id`, choose the lowest-ID protocol matching `preferred_protocol` when available, otherwise choose the lowest-ID eligible protocol, and apply weighted selection to one candidate per route. If any remaining candidates use the preferred protocol, select only within that tier; later failover calls may use conversion candidates after native route IDs are excluded.

- [ ] **Step 4: Run focused tests and verify GREEN**

  Run the Task 2 command.

### Task 3: Sync and Catalog Import/Export

**Files:**
- Modify: `src/ai_gateway/admin/model_sync.py`
- Modify: `src/ai_gateway/admin/configuration.py`
- Test: `tests/integration/catalog/test_sync.py`
- Test: `tests/integration/admin/test_configuration.py`

**Interfaces:**
- Discovery creates at most one route per `(provider_id, model_id)` regardless of discovery protocol.
- Exported catalog routes identify `provider` only; import resolves provider by name.

- [ ] **Step 1: Write failing sync and configuration tests**

  Assert multi-protocol discovery creates one provider route and exported route JSON omits `protocol` and `base_url`. Assert import merges by `(model, provider)`.

- [ ] **Step 2: Run focused tests and verify RED**

  Run: `GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/catalog/test_sync.py tests/integration/admin/test_configuration.py -q`

- [ ] **Step 3: Implement provider-level sync and catalog serialization**

  Key discovered routes by model ID, preserve manual routes, and disable only unseen discovered provider routes. Remove route protocol/base URL from catalog route validation and serialization while leaving provider protocol definitions unchanged.

- [ ] **Step 4: Run focused tests and verify GREEN**

  Run the Task 3 command.

### Task 4: History-Preserving Route Deletion

**Files:**
- Modify: `src/ai_gateway/admin/models.py`
- Test: `tests/integration/admin/test_catalog.py`

**Interfaces:**
- `DELETE /admin/model-routes/{route_id}` returns 204 for routes with or without request history.
- Existing history rows retain all fields except `model_route_id`, which becomes `NULL`.

- [ ] **Step 1: Change the existing history test to require deletion and detached logs**

  Assert the route is absent after deletion and the existing request log remains with `model_route_id is None`.

- [ ] **Step 2: Run the focused test and verify RED**

  Run: `GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/admin/test_catalog.py -q`

- [ ] **Step 3: Detach history before deleting**

  Execute `update(RequestLog).where(RequestLog.model_route_id == route_id).values(model_route_id=None)` before deleting the route in the same transaction. Remove the obsolete `model_route_has_history` error path.

- [ ] **Step 4: Run the focused test and verify GREEN**

  Run the Task 4 command.

### Task 5: Provider-Only Route Management UI

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/models/RouteFormDrawer.vue`
- Modify: `frontend/src/components/models/ModelCard.vue`
- Modify: `frontend/src/views/ModelsView.vue`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/tests/routes.spec.ts`
- Test: `frontend/tests/models.spec.ts`

**Interfaces:**
- Route create/update payloads and responses contain `provider_id` but no `provider_protocol_id`.
- The drawer exposes only a provider selector.
- Delete is always enabled when no other operation is running; a successful delete removes the route card.

- [ ] **Step 1: Write failing component tests**

  Assert the drawer has no provider-protocol selector, submits only `provider_id`, route cards display the provider and its enabled protocol labels, and a route with simulated history is deleted after a 204 response without offering the old disable-conflict flow.

- [ ] **Step 2: Run frontend route tests and verify RED**

  Run: `npm --prefix frontend run test -- routes.spec.ts models.spec.ts`

- [ ] **Step 3: Update UI types and components**

  Remove protocol IDs from route types and form state, derive displayed protocol labels from the selected provider, remove non-deletable-route state and `model_route_has_history` handling, and retain confirmation plus loading guards.

- [ ] **Step 4: Run frontend route tests and verify GREEN**

  Run the Task 5 command.

### Task 6: Full Verification

**Files:**
- Modify: `tests/contract/gateway/test_models.py`
- Modify: `tests/e2e/test_gateway.py`
- Modify: `tests/integration/admin/test_dashboard.py`
- Modify: `tests/integration/audit/test_request_logs.py`
- Modify: `tests/integration/gateway/test_failover.py`
- Modify: `tests/integration/gateway/test_stream_disconnect.py`
- Modify: `tests/unit/gateway/test_service_provider_integration.py`

- [ ] **Step 1: Run backend quality gates**

  Run:

  ```bash
  uv run ruff check src tests scripts
  uv run ruff format --check src tests scripts
  uv run mypy src scripts
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest -W error --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90
  ```

- [ ] **Step 2: Run frontend quality gates**

  Run:

  ```bash
  npm --prefix frontend run lint
  npm --prefix frontend run typecheck
  npm --prefix frontend run test
  npm --prefix frontend run build
  ```

- [ ] **Step 3: Verify migration and repository hygiene**

  Run: `docker compose config --quiet && docker build -t lean-ai-gateway:test . && git diff --check`
