# Cache Token Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add independently configurable cache-read and cache-write token prices, normalize provider cache usage without double-counting, and expose the resulting usage and prices throughout billing, audit, admin, and console surfaces.

**Architecture:** `CanonicalUsage` becomes four mutually exclusive buckets: uncached input, output, cache read, and cache write. Provider decoders normalize native totals into those buckets, protocol encoders reconstruct each provider's native totals/details, and billing prices each bucket independently before applying existing multipliers. Model catalog and request-log columns persist prices and observed cache usage, while reservation metadata snapshots all prices and recovery usage for deterministic retries.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic, pytest, Vue 3, TypeScript, Vitest.

## Global Constraints

- Preserve existing callers by defaulting both new usage buckets and both new model prices to zero.
- `CanonicalUsage.input_tokens` means uncached input only; all four token buckets are nonnegative and mutually exclusive.
- OpenAI Chat/Responses totals include cache read/write tokens, so decoders subtract both details from the native total and reject details whose sum exceeds that total.
- Claude `input_tokens` is already uncached; `cache_read_input_tokens` and `cache_creation_input_tokens` are copied directly.
- Gemini `promptTokenCount` includes `cachedContentTokenCount`; decoders subtract cached reads and expose no cache writes.
- Same-protocol passthrough remains byte-for-byte transport behavior; usage observation may parse cache details only for billing/audit metrics.
- Existing records and old reservation metadata without cache fields must continue to load with zero cache usage/prices.

---

### Task 1: Canonical usage and protocol normalization

**Files:**
- Modify: `src/ai_gateway/protocols/types.py`
- Modify: `src/ai_gateway/protocols/base.py`
- Modify: `src/ai_gateway/billing/usage.py`
- Modify: `src/ai_gateway/protocols/openai.py`
- Modify: `src/ai_gateway/protocols/claude.py`
- Modify: `src/ai_gateway/protocols/gemini.py`
- Modify: `src/ai_gateway/transport/sse.py`
- Test: `tests/unit/billing/test_usage.py`
- Test: `tests/contract/protocols/test_openai.py`
- Test: `tests/contract/protocols/test_openai_responses.py`
- Test: `tests/contract/protocols/test_claude.py`
- Test: `tests/contract/protocols/test_gemini.py`
- Test: `tests/contract/protocols/test_stream_events.py`
- Test: `tests/contract/protocols/test_strict_contracts.py`

**Interfaces:**
- Produces: `CanonicalUsage(input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_write_tokens: int = 0)`.
- Produces: provider decoders returning mutually exclusive usage buckets.
- Produces: provider encoders reconstructing native total input and cache detail fields.

- [ ] **Step 1: Write failing extraction and validation tests**

Add literal fixtures proving:

```python
assert extract_native_openai_usage("responses", payload) == CanonicalUsage(86, 20, 10, 4)
assert extract_provider_usage(Protocol.CLAUDE, payload) == CanonicalUsage(6, 7, 10, 4)
assert extract_provider_usage(Protocol.GEMINI, payload) == CanonicalUsage(90, 7, 10, 0)
```

Also assert negative cache values and OpenAI/Gemini cache details larger than total input are rejected.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `uv run pytest tests/unit/billing/test_usage.py tests/contract/protocols/test_strict_contracts.py -q`

Expected: failures because cache fields are absent and totals are not normalized.

- [ ] **Step 3: Implement canonical buckets and native decoders**

Add defaulted cache fields, validate all four fields, and use a helper equivalent to:

```python
def _exclusive_input(total: int, cache_read: int, cache_write: int, field: str) -> int:
    uncached = total - cache_read - cache_write
    if uncached < 0:
        raise UnsupportedFeatureError(field, "cache token details exceed total input tokens")
    return uncached
```

Read OpenAI snake-case detail objects, Claude top-level cache fields, and Gemini camel/snake-case cached-content fields.

- [ ] **Step 4: Run focused extraction tests and confirm GREEN**

Run: `uv run pytest tests/unit/billing/test_usage.py tests/contract/protocols/test_strict_contracts.py -q`

- [ ] **Step 5: Write failing protocol encode/decode and stream tests**

Assert OpenAI Chat/Responses encode total input plus `cached_tokens` and `cache_write_tokens`, Claude encodes four native fields, Gemini encodes total effective prompt plus cached read, and SSE usage merging retains maxima for all four buckets.

- [ ] **Step 6: Run protocol tests and confirm RED**

Run: `uv run pytest tests/contract/protocols/test_openai.py tests/contract/protocols/test_openai_responses.py tests/contract/protocols/test_claude.py tests/contract/protocols/test_gemini.py tests/contract/protocols/test_stream_events.py -q`

- [ ] **Step 7: Implement protocol encoders and stream observation**

Reconstruct native totals as:

```python
total_input = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
```

Update stateful stream accumulators and raw passthrough observers so cache buckets are merged independently and estimated usage retains observed cache buckets.

- [ ] **Step 8: Run protocol tests and confirm GREEN**

Run the command from Step 6.

### Task 2: Four-bucket pricing and deterministic billing recovery

**Files:**
- Modify: `src/ai_gateway/billing/pricing.py`
- Modify: `src/ai_gateway/billing/service.py`
- Test: `tests/unit/billing/test_pricing.py`
- Test: `tests/unit/billing/test_pricing_multipliers.py`
- Test: `tests/unit/billing/test_service_multipliers.py`
- Test: `tests/integration/billing/test_settlement.py`
- Test: `tests/integration/billing/test_review_regressions.py`

**Interfaces:**
- Consumes: four-bucket `CanonicalUsage` from Task 1.
- Produces: `PricedModel.cache_read_price_per_million` and `PricedModel.cache_write_price_per_million`.
- Produces: recovery metadata and fingerprints containing both cache prices and cache usage buckets.

- [ ] **Step 1: Write failing pricing tests**

Use one million tokens in each bucket with literal prices and assert:

```python
assert calculate_cost(model, CanonicalUsage(1_000_000, 1_000_000, 1_000_000, 1_000_000)) == Decimal("37.00000000")
```

for input `2`, output `20`, read `5`, write `10`; also assert negative cache prices fail and multipliers apply after summing all buckets.

- [ ] **Step 2: Run pricing tests and confirm RED**

Run: `uv run pytest tests/unit/billing/test_pricing.py tests/unit/billing/test_pricing_multipliers.py -q`

- [ ] **Step 3: Implement four-bucket pricing**

Extend both model-based and explicit-price paths, default explicit cache prices to zero for compatibility, validate all prices, sum four Decimal products, and quantize only once after multipliers.

- [ ] **Step 4: Run pricing tests and confirm GREEN**

Run the command from Step 2.

- [ ] **Step 5: Write failing recovery and idempotency tests**

Assert reservation snapshots contain both cache prices, recovery round-trips both cache token counts, settlement fingerprints distinguish cache usage, and legacy metadata missing new keys recovers with zero values.

- [ ] **Step 6: Run recovery tests and confirm RED**

Run: `uv run pytest tests/unit/billing/test_service_multipliers.py tests/integration/billing/test_settlement.py tests/integration/billing/test_review_regressions.py -q`

- [ ] **Step 7: Implement recovery snapshots and fingerprints**

Extend `_RecoveredModel`, reservation metadata, reservation/settlement fingerprints, `_recovery_metadata`, and `_reservation_recovery`. Read absent cache price/usage metadata as `Decimal("0")`/`0`.

- [ ] **Step 8: Run recovery tests and confirm GREEN**

Run the command from Step 6.

### Task 3: Persist model prices and request cache usage

**Files:**
- Create: `migrations/versions/0009_cache_token_pricing.py`
- Modify: `src/ai_gateway/db/models/catalog.py`
- Modify: `src/ai_gateway/db/models/audit.py`
- Modify: `src/ai_gateway/catalog/schemas.py`
- Modify: `src/ai_gateway/admin/models.py`
- Modify: `src/ai_gateway/audit/service.py`
- Modify: `src/ai_gateway/admin/request_logs.py`
- Modify: gateway call sites constructing `RequestResult` / `RequestFailure`
- Test: `tests/integration/test_schema.py`
- Test: `tests/integration/admin/test_catalog.py`
- Test: `tests/integration/admin/test_models.py`
- Test: `tests/integration/audit/test_request_logs.py`
- Test: `tests/unit/admin/test_schemas_price_multiplier.py`

**Interfaces:**
- Produces: model columns/API fields `cache_read_price_per_million`, `cache_write_price_per_million`.
- Produces: request-log columns/API fields `cache_read_tokens`, `cache_write_tokens`.

- [ ] **Step 1: Write failing schema and admin tests**

Assert migration head `0009`, all four columns exist as non-null numeric/integer fields with zero defaults, model create/update/list round-trip both prices, decimal precision validation matches existing price fields, and request-log detail returns both cache usage counts.

- [ ] **Step 2: Run schema/admin tests and confirm RED**

Run: `uv run pytest tests/unit/admin/test_schemas_price_multiplier.py tests/integration/admin/test_catalog.py tests/integration/admin/test_models.py tests/integration/audit/test_request_logs.py tests/integration/test_schema.py -q`

If database setup is unavailable, keep unit tests as the RED gate and run database tests once `GATEWAY_TEST_DATABASE_URL` is available.

- [ ] **Step 3: Implement migration, ORM, schemas, and admin mapping**

Add zero-default non-null price columns to `models`, zero-default non-null token columns to `request_logs`, expose them in catalog schemas/routes and request-log summaries/details, and update audit completion writes.

- [ ] **Step 4: Propagate cache usage into audit results**

Add defaulted cache fields to `RequestResult` and `RequestFailure`, and pass settled/observed canonical usage through every gateway success and failure path without changing existing positional callers.

- [ ] **Step 5: Run schema/admin tests and confirm GREEN**

Run the command from Step 2.

### Task 4: Console model pricing and request-log display

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/models/ModelFormDrawer.vue`
- Modify: `frontend/src/components/models/ModelCard.vue`
- Modify: `frontend/src/components/request-logs/RequestLogDetailDrawer.vue`
- Modify: `frontend/src/views/RequestLogsView.vue`
- Test: `frontend/tests/models.spec.ts`
- Test: `frontend/tests/request-logs.spec.ts`

**Interfaces:**
- Consumes: admin API fields from Task 3.
- Produces: create/update form controls and visible model/log cache pricing metrics.

- [ ] **Step 1: Write failing frontend tests**

Assert model cards show cache-read/write prices, create and update payloads include changed values, invalid decimal values block submission, dirty-state normalization matches existing input/output prices, request-log rows/detail show cache reads and writes, and absent/zero values render as zero.

- [ ] **Step 2: Run frontend tests and confirm RED**

Run: `npm test -- --run tests/models.spec.ts tests/request-logs.spec.ts`

- [ ] **Step 3: Implement frontend types, form, cards, and log views**

Follow the existing input/output price validation and normalized comparison pattern for both new fields. Keep labels explicit: `缓存读取价格`, `缓存写入价格`, `缓存读取 Token`, and `缓存写入 Token`.

- [ ] **Step 4: Run frontend tests and confirm GREEN**

Run the command from Step 2.

### Task 5: Regression verification and documentation consistency

**Files:**
- Modify as required by failing type checks or protocol fixtures only.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: a verified branch ready for integration.

- [ ] **Step 1: Run backend focused suites**

Run: `uv run pytest tests/unit/billing tests/contract/protocols tests/contract/gateway tests/unit/admin tests/integration/billing tests/integration/audit tests/integration/admin/test_catalog.py tests/integration/admin/test_models.py tests/integration/test_schema.py -q`

- [ ] **Step 2: Run backend static checks**

Run the repository's configured formatter, linter, and type-check commands from `pyproject.toml`/project scripts.

- [ ] **Step 3: Run frontend verification**

Run: `npm test -- --run`

Run: `npm run type-check`

Run: `npm run build`

- [ ] **Step 4: Inspect the final diff and status**

Run: `git diff --check && git status --short && git diff --stat`

Confirm no unrelated worktree or main-branch files are included.
