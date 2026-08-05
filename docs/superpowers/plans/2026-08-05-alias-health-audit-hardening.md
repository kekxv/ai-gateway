# Alias, Health, and Audit Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the five remaining defects after shared aliases were enabled.

**Architecture:** Neutral outcomes release half-open probes. UI and database enforce the intended alias rules. Migrations refuse a lossy downgrade before DDL. No-route HTTP calls receive a failed audit record without claiming a selected model.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic/MySQL, pytest, Vue 3, Vitest.

## Global Constraints

- Shared aliases remain valid across distinct model IDs.
- `(model_id, alias)` is unique.
- Neutral is neither a health success nor failure.
- No-route audit records `model_id=None` and `no_route_available`.
- Downgrade must fail before changing indexes when shared aliases exist.

---

### Task 1: Release neutral half-open probes

**Files:**
- Modify: `tests/integration/routing/test_health.py`
- Modify: `tests/contract/gateway/test_websocket.py`
- Modify: `src/ai_gateway/routing/health.py`
- Modify: `src/ai_gateway/gateway/websocket.py`

**Interfaces:** `record_failure` releases a half-open route when `is_health_failure` is false. WebSocket neutral relay results call `release_half_open`.

- [ ] **Step 1: Write failing tests**

```python
assert changed is True
assert route.runtime_state is RouteRuntimeState.OPEN
assert route_router.releases == [selected_route.route_id]
```

- [ ] **Step 2: Run red tests**

Run: `uv run pytest tests/integration/routing/test_health.py tests/contract/gateway/test_websocket.py -q`

- [ ] **Step 3: Implement and run green tests**

```python
if not is_health_failure(failure):
    return await self.release_half_open(route_id)
```

```python
elif result.health_outcome is RelayHealthOutcome.NEUTRAL:
    await _safe_health(route_router.release_half_open(route.route_id))
```

### Task 2: Permit model aliases equal to their own canonical name

**Files:**
- Modify: `frontend/tests/models.spec.ts`
- Modify: `frontend/src/components/models/ModelFormDrawer.vue`

**Interfaces:** Form submission accepts `canonical_name == alias`; a repeated alias row retains the duplicate error.

- [ ] **Step 1: Write failing test**

```ts
expect(onSubmit).toHaveBeenCalledWith({ aliases: [{ alias: 'gpt-4.1', enabled: true }] })
```

- [ ] **Step 2: Run red, remove only canonical-equality validation, run green**

Run: `npm --prefix frontend run test -- --run tests/models.spec.ts`

### Task 3: Enforce per-model alias uniqueness and safe downgrade

**Files:**
- Modify: `tests/integration/test_schema.py`
- Modify: `tests/integration/migrations/test_0015_shared_model_aliases.py`
- Modify: `src/ai_gateway/db/models/catalog.py`
- Modify: `migrations/versions/0015_shared_model_aliases.py`
- Create: `migrations/versions/0016_model_alias_per_model_unique.py`

**Interfaces:** Shared alias values remain valid across models. Duplicate `(model_id, alias)` is rejected. `0015.downgrade()` raises before index changes on duplicates.

- [ ] **Step 1: Write failing tests**

```python
assert ("model_id", "alias") in unique_column_sets("model_aliases")
with pytest.raises(RuntimeError, match="shared aliases"):
    await connection.run_sync(_downgrade_0015)
```

- [ ] **Step 2: Run red tests**

Run: `uv run pytest tests/integration/test_schema.py::test_required_unique_constraints_and_indexes_are_declared tests/integration/migrations/test_0015_shared_model_aliases.py -q`

- [ ] **Step 3: Add unique constraint, 0016 migration, and 0015 duplicate preflight; run green**

```python
UniqueConstraint("model_id", "alias", name="uq_model_aliases_model_alias")
```

### Task 4: Audit no-route HTTP requests

**Files:**
- Modify: `tests/contract/gateway/test_non_streaming.py`
- Modify: `src/ai_gateway/gateway/service.py`

**Interfaces:** A `NoRouteAvailable` from initial selection starts then fails an audit entry with the request model metadata, no selected model, and HTTP 503.

- [ ] **Step 1: Write failing test**

```python
assert audit.started is not None and audit.started.model_id is None
assert audit.failed is not None and audit.failed.error_code == "no_route_available"
```

- [ ] **Step 2: Run red, add narrow `except NoRouteAvailable`, and run green**

Run: `uv run pytest tests/contract/gateway/test_non_streaming.py::test_no_route_request_is_audited -q`

### Task 5: Verify and commit

- [ ] **Step 1: Run affected backend tests and CI static checks**

Run: `uv run pytest tests/integration/routing/test_health.py tests/contract/gateway/test_websocket.py tests/contract/gateway/test_non_streaming.py tests/integration/migrations/test_0015_shared_model_aliases.py tests/integration/test_schema.py -q`

- [ ] **Step 2: Run frontend lint, typecheck, tests, and build**

Run: `npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run test && npm --prefix frontend run build`

- [ ] **Step 3: Commit**

```bash
git add src tests frontend migrations docs/superpowers/plans/2026-08-05-alias-health-audit-hardening.md
git commit -m "fix: harden shared alias routing behavior"
```
