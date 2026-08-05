# Model Sync and Dashboard Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep aliases out of provider model synchronization and ensure the dashboard's 24-hour values are never confused with all-time totals.

**Architecture:** Provider discovery receives upstream string IDs; it must resolve only canonical model names, then creates a canonical model when no match exists. The admin dashboard has a bounded 24-hour query and separate all-time `total_*` fields; tests will make that distinction explicit before any dashboard behavior changes.

**Tech Stack:** FastAPI, SQLAlchemy async, MySQL-compatible integration tests, pytest, Vue 3.

## Global Constraints

- Shared aliases are valid only for request routing; they must not influence automatic provider synchronization.
- Manually created routes use the local integer `model_id`.
- The 24-hour window includes `now - 24h` through `now`, inclusive.
- `total_*` fields are all-time metrics and must be explicitly labelled as cumulative.

---

### Task 1: Restrict provider synchronization to canonical names

**Files:**
- Modify: `tests/integration/catalog/test_sync.py:207-300`
- Modify: `src/ai_gateway/admin/model_sync.py:397-416`

**Interfaces:**
- Consumes: `sync_provider_models(provider_id, session, http_client_factory, settings)`.
- Produces: discovered upstream ID `alias-native` creates or uses canonical model `alias-native`, rather than linking a model which merely has that alias.

- [ ] **Step 1: Write the failing test**

```python
assert model_names.count("alias-native") == 1
assert "alias-target" not in routes_by_model
assert routes_by_model["alias-native"].upstream_model == "alias-native"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/catalog/test_sync.py::test_sync_is_idempotent_preserves_aliases_and_never_mutates_manual_routes -q`

Expected: FAIL because the synchronizer resolves `alias-native` through `ModelAlias.alias`.

- [ ] **Step 3: Write minimal implementation**

```python
async def _models_by_discovered_name(session: AsyncSession, names: set[str]) -> dict[str, Model]:
    if not names:
        return {}
    canonical_models = list(
        await session.scalars(select(Model).where(Model.canonical_name.in_(names)))
    )
    return {model.canonical_name: model for model in canonical_models}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/catalog/test_sync.py::test_sync_is_idempotent_preserves_aliases_and_never_mutates_manual_routes -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/catalog/test_sync.py src/ai_gateway/admin/model_sync.py
git commit -m "fix: exclude aliases from provider model sync"
```

### Task 2: Lock dashboard 24-hour versus all-time semantics

**Files:**
- Modify: `tests/integration/admin/test_dashboard.py:265-335`
- Modify only if its red test reveals a mismatch: `src/ai_gateway/admin/dashboard.py:130-180` or `frontend/src/views/DashboardView.vue:88-122`

**Interfaces:**
- Consumes: `GET /admin/dashboard/summary` with fixed `now`.
- Produces: `requests_24h`, `cost_24h`, `cost_amount_24h`, and `gross_profit_24h` from the bounded 24-hour window; `total_*` stays explicitly all-time.

- [ ] **Step 1: Write the boundary assertions**

```python
assert payload["requests_24h"] == 6
assert payload["cost_24h"] == "0.16000000"
assert payload["cost_amount_24h"] == "0.05000000"
assert payload["gross_profit_24h"] == "0.11000000"
assert payload["total_requests"] == 10
```

- [ ] **Step 2: Run test to determine whether backend logic fails**

Run: `uv run pytest tests/integration/admin/test_dashboard.py::test_dashboard_summary_returns_counts_and_exact_seven_utc_days -q`

Expected: the assertions distinguish windowed and all-time data. If it passes, retain the query and inspect dashboard labels/API consumption for the reported display mismatch.

- [ ] **Step 3: Apply the smallest confirmed correction**

```python
.where(RequestLog.created_at >= cutoff_24h, RequestLog.created_at <= now)
```

All-time values must continue to use visibly cumulative UI text such as `累计`.

- [ ] **Step 4: Run focused backend and frontend tests**

Run: `uv run pytest tests/integration/admin/test_dashboard.py -q && npm --prefix frontend run test -- --run tests/dashboard.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit confirmed dashboard correction**

```bash
git add tests/integration/admin/test_dashboard.py src/ai_gateway/admin/dashboard.py frontend/src/views/DashboardView.vue
git commit -m "fix: keep dashboard windowed metrics scoped to 24 hours"
```

### Task 3: Validate affected CI checks

**Files:** None.

**Interfaces:**
- Consumes: `.github/workflows/ci.yml` commands.
- Produces: evidence that backend and frontend checks retain the requested behavior.

- [ ] **Step 1: Run focused regression tests**

Run: `uv run pytest tests/integration/catalog/test_sync.py tests/integration/admin/test_dashboard.py -q`

- [ ] **Step 2: Run static checks**

Run: `uv run ruff check src tests scripts && uv run ruff format --check src tests scripts && uv run mypy src scripts`

- [ ] **Step 3: Run frontend checks if frontend code changed**

Run: `npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run test && npm --prefix frontend run build`

- [ ] **Step 4: Report exact outcomes**

Report every failure and whether it is related; do not claim complete CI success unless every CI command passes.
