# Claude Token Count and Tiered Dual Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Claude-compatible token counting and introduce inclusive input-length pricing tiers with separate public charges and private provider costs throughout gateway billing, audit, reporting, configuration, and console workflows.

**Architecture:** Claude token counting authenticates the gateway key, decodes the Claude request locally, validates that at least one scoped route exists, and returns Anthropic's `{"input_tokens": N}` shape without reserving balance or calling an upstream. Model price tiers are normalized child rows selected by total input context (`input + cache read + cache write`), while the provider's renamed cost multiplier and new public multiplier independently calculate platform cost and user charge. The ledger debits only the public charge; request logs, recovery metadata, and admin reports also retain platform cost, which is never serialized by ordinary-user APIs.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic/MySQL 8.4, Pydantic 2, pytest, Vue 3, TypeScript, Element Plus, Vitest.

## Global Constraints

- Preserve all existing uncommitted request-log work and unrelated workspace content.
- `Length <= threshold` is inclusive and means uncached input tokens plus cache-read tokens plus cache-write tokens; output tokens never choose the tier.
- Configured bounded tier limits must be strictly increasing and the final tier must have `max_input_tokens = null`.
- Existing models without tier rows continue using their four legacy base price columns.
- A supplied non-empty tier list is authoritative and synchronizes the legacy base price columns to its first tier.
- Model `price_multiplier` applies to both calculations; provider `public_multiplier` calculates user charge and provider `cost_multiplier` calculates platform cost.
- `RequestLog.cost` remains the public/user fee for backward compatibility; new `RequestLog.cost_amount` stores private platform cost.
- Ordinary-user endpoints never serialize provider multipliers, provider identities, or `cost_amount`.
- User model pricing is shown as public minimum–maximum ranges across enabled routes because route selection is dynamic.
- Balance reservation uses the maximum public multiplier among eligible model routes and final settlement releases the difference.
- `/v1/messages/count_tokens` and `/anthropic/v1/messages/count_tokens` accept arbitrary query strings including `beta=true`, do not create audit/ledger entries, and use Claude-native error envelopes.

---

### Task 1: Claude-Compatible Token Counting

**Files:**
- Modify: `src/ai_gateway/gateway/claude.py`
- Modify: `src/ai_gateway/gateway/service.py`
- Modify: `src/ai_gateway/routing/service.py`
- Test: `tests/contract/gateway/test_non_streaming.py`

**Interfaces:**
- `GatewayService.count_claude_tokens(request: Request) -> GatewayOutput` returns JSON `{"input_tokens": int}`.
- `Router.has_eligible_route(model_id, principal, required_protocol=None) -> bool` performs a read-only eligibility check.
- The endpoint authenticates before parsing and accepts both gateway Claude paths.

- [ ] **Step 1: Write failing endpoint contract tests**

  Add real ASGI requests for `/v1/messages/count_tokens?beta=true` and `/anthropic/v1/messages/count_tokens`, using a catalog alias and Claude payload with system text, messages, and a tool. Assert status 200, content type JSON, an integer `input_tokens > 0`, zero billing settlements/reservations, zero upstream requests, and Claude error shape for malformed JSON or missing credentials.

- [ ] **Step 2: Verify RED**

  Run:

  ```bash
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/contract/gateway/test_non_streaming.py -k count_tokens -q
  ```

  Expected: both paths return 404.

- [ ] **Step 3: Implement the local count operation**

  Decode with `get_adapter(Protocol.CLAUDE).decode_request(payload)`, resolve aliases through `CatalogRepository`, verify a scoped route with a read-only router query, call `estimate_request_tokens`, and serialize via `orjson.dumps({"input_tokens": count})`.

- [ ] **Step 4: Verify GREEN**

  Run the Task 1 command and confirm all count-token cases pass.

### Task 2: Persist Price Tiers, Dual Multipliers, and Platform Cost

**Files:**
- Create: `migrations/versions/0014_tiered_dual_pricing.py`
- Create: `tests/unit/migrations/test_0014_tiered_dual_pricing.py`
- Modify: `src/ai_gateway/main.py`
- Modify: `src/ai_gateway/db/models/catalog.py`
- Modify: `src/ai_gateway/db/models/audit.py`
- Modify: `src/ai_gateway/db/models/__init__.py`
- Modify: `tests/integration/test_schema.py`
- Modify: `tests/unit/db/test_models_price_multiplier.py`

**Interfaces:**
- `Provider.cost_multiplier: Decimal` replaces the physical `price_multiplier` column and defaults to `1.00`.
- `Provider.public_multiplier: Decimal` defaults to `1.00`.
- `ModelPriceTier(model_id, max_input_tokens, four price columns)` belongs to `Model.price_tiers`.
- `RequestLog.cost_amount: Decimal` defaults to zero.
- Runtime migration head becomes `0014`.

- [ ] **Step 1: Write failing migration and ORM tests**

  Assert upgrade renames `providers.price_multiplier`, adds `providers.public_multiplier` and `request_logs.cost_amount`, creates `model_price_tiers` with a model foreign key/index, and that downgrade reverses each operation. Assert ORM defaults/types and relationships with literal table/column names.

- [ ] **Step 2: Verify RED**

  Run:

  ```bash
  uv run pytest tests/unit/migrations/test_0014_tiered_dual_pricing.py tests/unit/db/test_models_price_multiplier.py -q
  ```

- [ ] **Step 3: Implement migration and ORM mappings**

  Use `op.alter_column(..., new_column_name="cost_multiplier")`, `Numeric(4, 2)` multipliers, `Numeric(20, 8)` money/prices, `BigInteger` nullable tier bounds, `ondelete="CASCADE"`, and ordered `Model.price_tiers` relationships.

- [ ] **Step 4: Verify GREEN**

  Run Task 2 tests plus:

  ```bash
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/test_schema.py -q
  ```

### Task 3: Select Inclusive Tiers and Calculate Charge/Cost Independently

**Files:**
- Modify: `src/ai_gateway/billing/pricing.py`
- Modify: `src/ai_gateway/billing/multipliers.py`
- Test: `tests/unit/billing/test_pricing.py`
- Test: `tests/unit/billing/test_pricing_multipliers.py`

**Interfaces:**
- `PriceTier` protocol exposes `max_input_tokens` plus four prices.
- `select_price_tier(model, usage) -> PricedModel` uses total input context and inclusive limits.
- `calculate_cost` prices all token buckets using the selected tier before multiplying.
- `get_effective_multipliers(model, provider) -> tuple[Decimal, Decimal, Decimal]` returns model, public-provider, and cost-provider multipliers.

- [ ] **Step 1: Write failing boundary and dual-multiplier tests**

  With literal tiers `<=272000` and unbounded, assert lengths `271999` and `272000` use tier one, `272001` uses tier two, cache tokens contribute to length, output tokens do not, empty tiers fall back to model prices, public charge uses public multiplier, and platform cost uses cost multiplier.

- [ ] **Step 2: Verify RED**

  ```bash
  uv run pytest tests/unit/billing/test_pricing.py tests/unit/billing/test_pricing_multipliers.py -q
  ```

- [ ] **Step 3: Implement deterministic tier selection**

  Sort bounded tiers before the unbounded tier, reject a missing matching tier, keep Decimal-only arithmetic, and retain one final eight-decimal `ROUND_HALF_UP` quantization.

- [ ] **Step 4: Verify GREEN**

  Run the Task 3 command.

### Task 4: Settle, Recover, and Audit Both Monetary Values

**Files:**
- Modify: `src/ai_gateway/billing/service.py`
- Modify: `src/ai_gateway/gateway/service.py`
- Modify: `src/ai_gateway/gateway/websocket.py`
- Modify: `src/ai_gateway/audit/service.py`
- Modify: `src/ai_gateway/admin/request_logs.py`
- Modify: `tests/unit/billing/test_service_multipliers.py`
- Modify: `tests/integration/billing/test_service.py`
- Modify: `tests/integration/audit/test_request_logs.py`
- Modify: `tests/contract/gateway/test_non_streaming.py`
- Modify: `tests/contract/gateway/test_streaming.py`
- Modify: `tests/contract/gateway/test_websocket.py`

**Interfaces:**
- `SettlementResult.cost_amount` is platform cost while `actual_cost` remains public charge for compatibility.
- `ReservationRecovery.cost_amount` snapshots private cost beside its public `cost`.
- `BillingService.reserve_balance(..., provider_public_multiplier=None)` supports maximum-route reservation pricing.
- `RequestResult`/`RequestFailure` and admin request-log responses include `cost_amount`; user responses do not.

- [ ] **Step 1: Write failing settlement/recovery/audit tests**

  Assert a base `10.00` calculation with model `1.50`, public `2.00`, and cost `0.80` yields a public charge of `30.00` and platform cost `12.00`; only `30.00` debits balance. Assert recovery replay preserves both values, request logs store both, admin sees both, and ordinary users cannot see `cost_amount`.

- [ ] **Step 2: Verify RED**

  Run focused billing, audit, and gateway contract tests.

- [ ] **Step 3: Implement dual monetary propagation**

  Snapshot tiers and both multipliers in reservation metadata/fingerprints, calculate both values once after final usage/provider selection, persist both in recovery metadata and ledger usage metadata, and pass `cost_amount` through every success/failure/stream/WebSocket audit terminal path.

- [ ] **Step 4: Verify GREEN**

  Run:

  ```bash
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/unit/billing tests/integration/billing tests/integration/audit/test_request_logs.py tests/contract/gateway -q
  ```

### Task 5: Expose and Validate Tiered Pricing Configuration

**Files:**
- Modify: `src/ai_gateway/catalog/schemas.py`
- Modify: `src/ai_gateway/admin/models.py`
- Modify: `src/ai_gateway/admin/providers.py`
- Modify: `src/ai_gateway/admin/audit.py`
- Modify: `src/ai_gateway/admin/configuration.py`
- Modify: `src/ai_gateway/catalog/repository.py`
- Modify: `tests/unit/admin/test_schemas_price_multiplier.py`
- Modify: `tests/integration/admin/test_models.py`
- Modify: `tests/integration/admin/test_providers.py`
- Modify: `tests/integration/admin/test_configuration.py`

**Interfaces:**
- Model create/update/response adds `price_tiers` with inclusive nullable upper bounds.
- Provider create/update/response uses `cost_multiplier` and `public_multiplier`, accepting legacy `price_multiplier` only as an input alias for `cost_multiplier`.
- User model response adds aggregate `public_price_tiers` ranges and excludes provider multiplier fields.
- Catalog import accepts legacy provider `price_multiplier`; export emits the two explicit multipliers and model tiers.
- Multiplier audit actions identify `cost_multiplier`, `public_multiplier`, or model `price_multiplier`.

- [ ] **Step 1: Write failing schema/API/configuration tests**

  Assert invalid duplicate/non-increasing/no-unbounded tiers return 422, valid two-tier CRUD round-trips exact decimals, first tier synchronizes base fields, legacy providers import into cost multiplier, both multipliers export, and user public ranges equal hand-calculated route minima/maxima without provider fields.

- [ ] **Step 2: Verify RED**

  Run focused schema, model, provider, and configuration tests.

- [ ] **Step 3: Implement validation and transactional tier replacement**

  Use a Pydantic after-validator for tier ordering, replace child rows inside existing model transactions, eager-load tiers wherever serialized/priced, aggregate public price ranges over enabled provider routes, and log each changed multiplier separately.

- [ ] **Step 4: Verify GREEN**

  Run:

  ```bash
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/unit/admin tests/integration/admin -q
  ```

### Task 6: Optimize Admin/User Reporting and Console Pricing UX

**Files:**
- Modify: `src/ai_gateway/admin/dashboard.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/providers/ProviderFormDrawer.vue`
- Modify: `frontend/src/components/providers/ProviderCard.vue`
- Modify: `frontend/src/components/models/ModelFormDrawer.vue`
- Modify: `frontend/src/components/models/ModelCard.vue`
- Modify: `frontend/src/views/DashboardView.vue`
- Modify: `frontend/src/views/RequestLogsView.vue`
- Modify: `frontend/src/components/request-logs/RequestLogDetailDrawer.vue`
- Modify: `frontend/tests/providers.spec.ts`
- Modify: `frontend/tests/models.spec.ts`
- Modify: `frontend/tests/dashboard.spec.ts`
- Modify: `frontend/tests/request-logs.spec.ts`
- Modify: `tests/integration/admin/test_dashboard.py`

**Interfaces:**
- Provider forms/cards label and edit separate `成本倍率` and `公开倍率`.
- Model forms support add/remove tier rows with an inclusive upper-bound field and four exact price fields.
- Ordinary-user model cards render effective public price ranges; admin cards render configured base tiers.
- Admin dashboard adds 24-hour platform cost and gross profit; admin logs show user fee and platform cost, while user logs show only fee.

- [ ] **Step 1: Write failing frontend/report tests**

  Assert provider payloads contain both multipliers, tier form rows preserve exact strings and ordering, user cards show public ranges without provider/cost data, admin request rows/details show both fee values, ordinary users show only user fee, and dashboard gross profit equals public fees minus platform costs.

- [ ] **Step 2: Verify RED**

  Run:

  ```bash
  npm --prefix frontend run test -- providers.spec.ts models.spec.ts dashboard.spec.ts request-logs.spec.ts
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/admin/test_dashboard.py -q
  ```

- [ ] **Step 3: Implement the role-aware console UX**

  Reuse existing decimal validation, use `null` for the final unbounded tier, label limits as `长度 <= N`, format min/max ranges without exposing provider identity, and retain current stale-request/cancellation guards.

- [ ] **Step 4: Verify GREEN**

  Run the Task 6 commands.

### Task 7: Documentation and Full Verification

**Files:**
- Modify: `docs/protocol-compatibility.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Review all changed files and preserve prior request-log edits.

**Interfaces:**
- Documentation defines count-token compatibility, tier boundary semantics, and private/public monetary terminology.

- [ ] **Step 1: Document operator-visible behavior**

  Add the two count-token paths, explain that local counts are gateway estimates, document inclusive total-input tiers, and state that ordinary users see public price ranges while administrators see cost/profit.

- [ ] **Step 2: Run backend quality gates**

  ```bash
  uv run ruff check src tests scripts
  uv run ruff format --check src tests scripts
  uv run mypy src scripts
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest -q
  ```

- [ ] **Step 3: Run frontend quality gates**

  ```bash
  npm --prefix frontend run lint
  npm --prefix frontend run typecheck
  npm --prefix frontend run test
  npm --prefix frontend run build
  ```

- [ ] **Step 4: Run repository gates and requirement review**

  ```bash
  docker compose config --quiet
  git diff --check
  git status --short
  ```

  Recheck token-count routing, inclusive tier boundaries, public charge, private cost, role visibility, reservation/recovery consistency, configuration round-trip, dashboard profit, and all prior request-log requirements against the final diff.
