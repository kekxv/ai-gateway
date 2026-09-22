# Peak and Off-Peak Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Apply the announced DeepSeek peak/off-peak price schedule automatically at billing time, using Beijing time from 2026-08-17 00:00 onward.

**Architecture:** Store an optional, model-level peak/off-peak price schedule alongside existing input-length tiers. The pricing module resolves a single effective schedule from an injected UTC timestamp, so both reservations and settlement use the same explicit time basis and remain deterministic in tests. Existing prices and price tiers remain the fallback before the effective date or for models without a schedule.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async ORM, Alembic/MySQL, Pydantic, pytest, Vue 3/TypeScript.

## Global Constraints

- Beijing time is \`Asia/Shanghai\`; peak windows are 09:00–12:00 and 14:00–18:00, with start inclusive and end exclusive.
- The schedule is effective only from 2026-08-17T00:00:00+08:00; all earlier calls retain existing pricing.
- Off-peak prices are explicitly configured, not calculated from peak prices, so future exceptions are representable.
- Price selection must use the reservation timestamp for both reservation and settlement of one request, preventing a request spanning a boundary from changing its rate.
- All price and ledger arithmetic stays in \`Decimal\` and retains 8-decimal half-up rounding.
- Existing models without a schedule, existing input-length tiers, model multipliers, and provider multipliers retain their current behavior.

---

## File Structure

- Modify \`src/ai_gateway/db/models/catalog.py\`: add a model pricing-schedule relationship and schedule/period price persistence model.
- Create \`migrations/versions/0019_peak_off_peak_pricing.py\`: create the schedule-price table, FK, uniqueness, and indexes.
- Modify \`src/ai_gateway/billing/pricing.py\`: resolve peak versus off-peak prices from an explicit timestamp before applying length tiers and multipliers.
- Modify \`src/ai_gateway/billing/service.py\`: capture the reservation time, persist the selected period and price snapshot, and reuse it during settlement/recovery.
- Modify \`src/ai_gateway/catalog/schemas.py\`, \`src/ai_gateway/admin/models.py\`, and \`src/ai_gateway/admin/configuration.py\`: expose schedule configuration through catalog APIs/import-export.
- Modify \`frontend/src/api/types.ts\`, \`frontend/src/components/models/ModelFormDrawer.vue\`, and \`frontend/src/components/models/ModelCard.vue\`: configure and display the optional schedule.
- Add/modify focused unit, migration, admin integration, billing integration, and frontend tests.

### Task 1: Define and test time-period price selection

**Files:**
- Modify: \`tests/unit/billing/test_pricing.py\`
- Modify: \`src/ai_gateway/billing/pricing.py\`

**Interfaces:**
- Produces: \`select_time_period(at: datetime) -> Literal["peak", "off_peak"]\` and \`select_effective_price(model: PricedModel, usage: CanonicalUsage, at: datetime) -> PricedModel\`.

- [ ] **Step 1: Write failing unit tests**

Add table-driven tests with literal UTC timestamps for 2026-08-16 23:59:59+08:00, 2026-08-17 00:00:00+08:00, 08:59:59, 09:00:00, 12:00:00, 14:00:00, and 18:00:00. Assert the selected period and cost for a model whose peak input/output/cache prices are 3/9/1/2 and off-peak prices are 1.5/4.5/0.5/1.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: \`pytest tests/unit/billing/test_pricing.py -q\`

Expected: FAIL because time-period schedule resolution is absent.

- [ ] **Step 3: Implement the smallest resolver**

Add timezone-aware timestamp normalization, the 2026-08-17 Beijing effective-date guard, and inclusive/exclusive peak-window selection. Resolve an explicit schedule price first, then continue through the existing input-length tier selection and cost calculation.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: \`pytest tests/unit/billing/test_pricing.py -q\`

Expected: PASS.

### Task 2: Persist schedules and expose validated catalog configuration

**Files:**
- Create: \`migrations/versions/0019_peak_off_peak_pricing.py\`
- Modify: \`src/ai_gateway/db/models/catalog.py\`
- Modify: \`src/ai_gateway/catalog/schemas.py\`
- Modify: \`src/ai_gateway/admin/models.py\`
- Modify: \`src/ai_gateway/admin/configuration.py\`
- Test: \`tests/unit/migrations/test_0019_peak_off_peak_pricing.py\`
- Test: \`tests/unit/admin/test_schemas_price_multiplier.py\`
- Test: \`tests/integration/admin/test_models.py\`

**Interfaces:**
- Consumes: the price-period names from Task 1.
- Produces: API fields for an optional \`peak_off_peak_prices\` object with \`peak\` and \`off_peak\` four-price values; each is validated by the existing nonnegative 20,8 Decimal price type.

- [ ] **Step 1: Write failing schema, API, and migration tests**

Assert that an admin can create/update/read a model schedule, catalog export/import round-trips it, invalid/missing period payloads return validation errors, and the migration creates a model FK with cascade plus a unique \`(model_id, period)\` constraint.

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: \`pytest tests/unit/migrations/test_0019_peak_off_peak_pricing.py tests/unit/admin/test_schemas_price_multiplier.py tests/integration/admin/test_models.py -q\`

Expected: FAIL because neither schema nor table exists.

- [ ] **Step 3: Implement storage, migration, schemas, and API mapping**

Create one child row per period with the four price columns. Add create/update/read/import/export conversion that replaces the two rows atomically when the object is supplied and leaves schedules unchanged on partial model updates that omit it.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run: \`pytest tests/unit/migrations/test_0019_peak_off_peak_pricing.py tests/unit/admin/test_schemas_price_multiplier.py tests/integration/admin/test_models.py -q\`

Expected: PASS.

### Task 3: Make reservations and settlement boundary-safe and auditable

**Files:**
- Modify: \`src/ai_gateway/billing/service.py\`
- Test: \`tests/unit/billing/test_service_multipliers.py\`
- Test: \`tests/integration/billing/test_settlement.py\`

**Interfaces:**
- Consumes: Task 1 effective price selection and Task 2 ORM schedule relationship.
- Produces: reservation ledger metadata including \`pricing_period\`, \`pricing_at\`, and all four selected price values; settlement reuses this snapshot rather than current wall-clock pricing.

- [ ] **Step 1: Write failing billing tests**

Use an injectable \`now\` argument or clock dependency to assert an off-peak reservation at 08:59 Beijing prices the request at the off-peak rate, then settlement at 09:01 charges the same off-peak rate. Add the inverse boundary test and assert ledger metadata records the period and exact selected prices.

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: \`pytest tests/unit/billing/test_service_multipliers.py tests/integration/billing/test_settlement.py -q\`

Expected: FAIL because billing does not persist a time-period price snapshot.

- [ ] **Step 3: Implement snapshot-based billing**

Capture UTC at reservation, pass it to pricing, store the resolved period and price snapshot in ledger metadata/fingerprint, and use that snapshot for normal settlement and recovery. Preserve exact idempotency replay behavior by including the snapshot in the fingerprint.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run: \`pytest tests/unit/billing/test_service_multipliers.py tests/integration/billing/test_settlement.py -q\`

Expected: PASS.

### Task 4: Configure and show peak/off-peak prices in the web console

**Files:**
- Modify: \`frontend/src/api/types.ts\`
- Modify: \`frontend/src/components/models/ModelFormDrawer.vue\`
- Modify: \`frontend/src/components/models/ModelCard.vue\`
- Test: \`frontend/tests/models.spec.ts\`

**Interfaces:**
- Consumes: Task 2's \`peak_off_peak_prices\` request/response object.
- Produces: form payloads with both required periods and a model-card display that states Beijing-time peak windows and effective date.

- [ ] **Step 1: Write failing frontend tests**

Assert that an administrator can enable the schedule, enter all four prices for both periods, submit the expected API payload, and that a user-visible model card displays the peak and off-peak prices plus “北京时间 09:00–12:00、14:00–18:00；2026-08-17 起生效”.

- [ ] **Step 2: Run the focused frontend test to verify it fails**

Run: \`cd frontend && npm test -- --run tests/models.spec.ts\`

Expected: FAIL because schedule fields are absent.

- [ ] **Step 3: Implement the minimal UI and type changes**

Add nullable schedule types, a single enable/disable control with two price rows, client-side decimal validation matching the API, and a compact read-only schedule display. Do not alter existing basic/tier price behavior when no schedule is present.

- [ ] **Step 4: Run the focused frontend test to verify it passes**

Run: \`cd frontend && npm test -- --run tests/models.spec.ts\`

Expected: PASS.

### Task 5: Verify the complete change

**Files:**
- Modify only if checks reveal a defect.

- [ ] **Step 1: Run Python format/lint/type checks**

Run: \`ruff check src tests && mypy src\`

Expected: exit 0.

- [ ] **Step 2: Run the Python suite**

Run: \`pytest -q\`

Expected: exit 0.

- [ ] **Step 3: Run frontend checks**

Run: \`cd frontend && npm run lint && npm run test -- --run && npm run build\`

Expected: all commands exit 0.

- [ ] **Step 4: Review requirements against evidence**

Confirm date gating, both peak windows, all boundary transitions, all four token price categories, DeepSeek v4 flash/pro prices, reservation/settlement snapshot consistency, migration reversibility, API/import-export, UI configuration/display, and regression coverage.
