# Review Findings Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the five defects found while reviewing shared model alias routing before it is merged into `main`.

**Architecture:** Release request-owned database connections before isolated audit writes, and treat cancelled or disconnected half-open probes as neutral outcomes that return to `OPEN`. Make public model selector grouping use the same case-insensitive identity as MySQL lookups, then correct the remaining admin conflict response without changing the shared-alias database rule.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, MySQL 8.4, pytest, Vue 3, Ruff, mypy.

**Status:** Implementation and verification executed on 2026-08-05. The five targeted
regressions and all affected suites pass. The full CI-equivalent run still exposes two
pre-existing authentication/test-harness failures documented under Task 6.

## Global Constraints

- Shared aliases remain valid across distinct model IDs.
- `(model_id, alias)` remains unique.
- Canonical names and aliases may be the same selector.
- Retries remain pinned to the model chosen by the initial weighted route.
- Neutral probe outcomes must not count as success or failure and must not remain `HALF_OPEN`.
- Do not commit unless the user explicitly asks for a commit.

---

### Task 1: Release the request connection before no-route audit writes

**Files:**
- Modify: `tests/integration/gateway/test_pool_lifecycle.py`
- Modify: `src/ai_gateway/gateway/service.py:317-346`

**Interfaces:**
- Consumes: `AuditService`, the request-owned `AsyncSession`, and `_release_read_session(session)`.
- Produces: a failed real `RequestLog` for a no-route request even when the engine has `pool_size=1` and `max_overflow=0`.

- [ ] **Step 1: Add a real-pool regression test**

Create a model without routes, authenticate through the gateway using the same one-connection engine for the request and `AuditService`, issue a completion request, and assert HTTP 503 plus a persisted failed `RequestLog` with `error_code="no_route_available"`.

- [ ] **Step 2: Run the regression test and verify RED**

Run: `uv run pytest tests/integration/gateway/test_pool_lifecycle.py::test_no_route_audit_does_not_self_exhaust_pool_size_one -q`

Expected: FAIL because the audit insert cannot obtain the connection still held by the request session.

- [ ] **Step 3: Release the request read session before starting the isolated audit**

In the narrow `except NoRouteAvailable` branch, call `await _release_read_session(self._session)` before `AuditService.start_request()`.

- [ ] **Step 4: Run the regression test and verify GREEN**

Run the command from Step 2 and expect PASS.

### Task 2: Release cancelled WebSocket half-open probes

**Files:**
- Modify: `tests/contract/gateway/test_websocket.py`
- Modify: `src/ai_gateway/gateway/websocket.py:586-756`

**Interfaces:**
- Consumes: `RouteSelector.release_half_open(route_id)` and `RouteCandidate.runtime_state`.
- Produces: exactly one neutral release when `WebSocketGatewayService.handle()` is cancelled while `relay_websocket()` is active.

- [ ] **Step 1: Add a gateway-level cancellation regression test**

Patch authentication and catalog resolution, make the relay signal that it started and then block forever, cancel the service task, and assert that the selected half-open route ID appears once in `FakeRouter.releases` with no success or failure update.

- [ ] **Step 2: Run the regression test and verify RED**

Run: `uv run pytest tests/contract/gateway/test_websocket.py::test_gateway_cancellation_releases_active_half_open_probe -q`

Expected: FAIL because `relay_started=True` suppresses the finally release.

- [ ] **Step 3: Track whether route health reached a terminal outcome**

Replace the relay-started condition with a route-health-finalized flag. Set it only after success, failure, or neutral health handling completes; in shielded cleanup, release a selected half-open route whenever health was not finalized.

- [ ] **Step 4: Run the regression test and existing WebSocket health tests**

Run: `uv run pytest tests/contract/gateway/test_websocket.py -q`

Expected: PASS.

### Task 3: Release neutral HTTP stream half-open probes

**Files:**
- Modify: `tests/integration/gateway/test_stream_disconnect.py`
- Modify: `src/ai_gateway/gateway/service.py:774-920`

**Interfaces:**
- Consumes: `_release_unstarted_half_open(router, route)`.
- Produces: `OPEN` for a half-open route after downstream disconnect, response-start failure, or an explicitly closed stream iterator; upstream stream errors still use `record_failure`.

- [ ] **Step 1: Change the stream termination test to require a neutral release**

Extend `RecordingRouter` with `release_half_open()`, record releases, and require every non-upstream-error termination to release route 41 and move the fake runtime state to `OPEN`.

- [ ] **Step 2: Run the stream termination test and verify RED**

Run: `uv run pytest tests/integration/gateway/test_stream_disconnect.py -q`

Expected: FAIL because `_finalize_stream()` returns before any neutral health operation.

- [ ] **Step 3: Release the half-open probe before returning from neutral stream termination**

In `_finalize_stream()`, call `_release_unstarted_half_open(router, route)` when `disconnected` or `downstream_failed`, then return without recording success or failure.

- [ ] **Step 4: Run the stream termination test and verify GREEN**

Run the command from Step 2 and expect PASS.

### Task 4: Deduplicate case-insensitive public model selectors

**Files:**
- Modify: `tests/contract/gateway/test_models.py`
- Modify: `src/ai_gateway/gateway/models.py:79-162`

**Interfaces:**
- Produces: `_selector_key(name: str) -> str`, used both for grouping public selectors and matching detail endpoints.
- Preserves: the spelling of the first deterministic model/alias entry as the public selector ID.

- [ ] **Step 1: Add a case-variant shared-selector regression test**

Create two routable models whose aliases are `shared-case-selector` and `SHARED-CASE-SELECTOR`. Assert the list contains one case-insensitive selector and both case variants resolve through the detail endpoint to that same public selector ID.

- [ ] **Step 2: Run the regression test and verify RED**

Run: `uv run pytest tests/contract/gateway/test_models.py::test_model_list_deduplicates_case_insensitive_shared_selectors -q`

Expected: FAIL because the Python dictionary currently treats both spellings as different keys.

- [ ] **Step 3: Normalize selector identity with `str.casefold()`**

Order models by ID, group canonical names and aliases by `_selector_key`, preserve the first spelling for output, and use the same key for OpenAI and Claude detail lookup.

- [ ] **Step 4: Run model contract tests and verify GREEN**

Run: `uv run pytest tests/contract/gateway/test_models.py -q`

Expected: PASS.

### Task 5: Correct the admin model conflict response

**Files:**
- Modify: `tests/integration/admin/test_models.py`
- Modify: `src/ai_gateway/admin/models.py:557-562`

**Interfaces:**
- Produces: a conflict message stating that canonical names are globally unique while aliases are unique only within one model.

- [ ] **Step 1: Add an API regression test for the conflict response**

Create one model with two aliases that differ only by case. Python request validation accepts the distinct strings, MySQL rejects them as the same per-model alias, and the response must be HTTP 409 with `code="model_conflict"` plus an accurate message that does not claim aliases are globally unique.

- [ ] **Step 2: Run the regression test and verify RED**

Run: `uv run pytest tests/integration/admin/test_models.py::test_admin_model_conflict_describes_shared_alias_rules -q`

Expected: FAIL on the old globally-unique-alias message.

- [ ] **Step 3: Update `_raise_model_conflict()`**

Use: `Canonical model names must be unique; aliases must be unique within each model`.

- [ ] **Step 4: Run the regression test and verify GREEN**

Run the command from Step 2 and expect PASS.

### Task 6: Full verification against CI workflow

**Files:**
- Verify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: fresh evidence for backend tests, coverage, static analysis, frontend checks/build/tests, Compose validation, and production image build.

- [ ] **Step 1: Run affected regression suites**

Run all files changed above with the CI database environment.

- [ ] **Step 2: Run backend CI commands**

Run Ruff lint/format, mypy, and the full pytest coverage command from `ci.yml`.

- [ ] **Step 3: Run frontend CI commands**

Run frontend lint, typecheck, tests, and build.

- [ ] **Step 4: Run remaining local CI validations**

Validate both Compose files and build the production Docker image. Browser E2E is run only if Chromium and its system dependencies are already available locally; otherwise report that exact CI-only gap without claiming it passed.

**Observed verification:** affected backend suites passed (68 tests); Ruff lint/format,
mypy, frontend lint/typecheck/unit tests/build, Compose validation, migrations, coverage
(90.98%), and the production image build passed. The complete backend suite reported
1151 passed and one pre-existing refresh-token replay failure. Browser E2E reported two
passed and five failures because the application uses `localStorage` while those existing
tests inject/clear `sessionStorage`, leaking login and registration state between cases.
