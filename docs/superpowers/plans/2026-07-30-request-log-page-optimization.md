# Request Log Page Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make request-log filters compact and human-readable, keep provider data admin-only, display API-key names, and combine protocol/transport/status metadata into one tag-based table column.

**Architecture:** The admin and user log APIs will project API-key names, while the user API will stop selecting, filtering, and serializing provider and route identity data. The Vue page will load role-appropriate user/key/model/provider catalogs for native select filters, use a compact filter toolbar, and render one tag cluster for request execution metadata. The detail drawer will follow the same role-specific provider visibility rule.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, pytest, Vue 3, TypeScript, Element Plus, Vitest.

## Global Constraints

- Ordinary-user API responses and UI must not expose provider IDs, provider names, model-route IDs, or upstream model names.
- Ordinary users must not request provider catalog data or send a `provider_id` request-log filter.
- Search controls must use readable labels while continuing to send stable numeric IDs to existing admin filters.
- Request-log rows must show API-key names instead of key prefixes.
- Protocol, transport/streaming, and status/HTTP data must occupy one table column and render as tags.
- Preserve cursor pagination, stale-request cancellation, detail redaction, and all unrelated working-tree content.

---

### Task 1: Harden Request-Log Identity Projections

**Files:**
- Modify: `src/ai_gateway/admin/request_logs.py`
- Modify: `src/ai_gateway/user/request_logs.py`
- Test: `tests/integration/audit/test_request_logs.py`

**Interfaces:**
- Admin `RequestLogSummary` adds `api_key_name: str | None` and retains provider/route identity fields.
- User `RequestLogSummary` adds `api_key_name: str | None` and has no provider/route identity fields.
- `/user/request-logs` no longer accepts `provider_id`.

- [x] **Step 1: Write failing projection and privacy assertions**

  Update the existing admin and user list/detail integration cases with literal assertions:

  ```python
  assert item["api_key_name"] == "audit-key"
  for field in ("provider_id", "provider_name", "model_route_id", "route_upstream_model"):
      assert field not in user_item
  ```

  Verify the returned log still follows the authenticated-user boundary while none of the provider/route fields are serialized.

- [x] **Step 2: Run the focused test and verify RED**

  Run:

  ```bash
  uv run pytest tests/integration/audit/test_request_logs.py -q
  ```

  Expected: `api_key_name` is absent and user responses still contain provider/route fields.

- [x] **Step 3: Implement the minimal projections**

  Label `ApiKey.name` as `api_key_name` in both queries. Remove `RequestLog.provider_id`, `RequestLog.model_route_id`, `Provider`, and `ModelRoute` from the user response/query, remove `provider_id` from the user route signature and `_apply_filters`, and keep all admin fields intact.

- [x] **Step 4: Run the focused test and verify GREEN**

  Run the Task 1 command and confirm the new API contract passes.

### Task 2: Add Friendly Role-Aware Filter Options

**Files:**
- Modify: `frontend/src/api/requestLogs.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/views/RequestLogsView.vue`
- Test: `frontend/tests/request-logs.spec.ts`

**Interfaces:**
- Admin filter options come from `listUsers`, `listApiKeys`, `listModels`, and `listProviders`.
- User filter options come from `listOwnApiKeys` and `listAvailableModels`; no provider request is made.
- Select values remain numeric IDs and serialize through the existing admin query keys.

- [x] **Step 1: Write failing admin and user filter tests**

  Mount with complete catalog fixtures and assert the controls are selects whose visible options include `audit-member@example.com`, `Audit Key`, `Audit Model`, and `audit-provider`. Select them and assert the log request contains literal ID parameters. Mount as a normal user and assert there is no provider control or provider request.

- [x] **Step 2: Run the frontend test and verify RED**

  Run:

  ```bash
  npm --prefix frontend run test -- request-logs.spec.ts
  ```

  Expected: ID inputs remain, friendly options are absent, and ordinary-user queries still support `provider_id`.

- [x] **Step 3: Implement role-aware option loading and selects**

  Load allowed catalogs with one abort controller, store their complete response types, render native selects, label models with `display_name`, and label admin keys as `name · owner email` when the user is known. Remove `providerId` from `userQueryParams` and omit the provider control for ordinary users.

- [x] **Step 4: Verify GREEN**

  Run the Task 2 command and confirm option labels, ID serialization, role visibility, and request cancellation pass.

### Task 3: Compact Filters and Consolidate Log Metadata

**Files:**
- Modify: `frontend/src/views/RequestLogsView.vue`
- Modify: `frontend/src/components/request-logs/RequestLogDetailDrawer.vue`
- Test: `frontend/tests/request-logs.spec.ts`

**Interfaces:**
- The filter panel has a compact inline heading/action bar and dense auto-fitting controls without descriptive vertical padding.
- The list has one `请求信息` column for protocol direction, transport/streaming, status, and HTTP status tags.
- Admin model cells and detail show provider/upstream data; ordinary-user cells and detail show only model data.

- [x] **Step 1: Write failing layout and visibility tests**

  Assert the old three headings are absent, `请求信息` exists, and one row contains separate tag texts for `Claude → OpenAI`, `HTTP`, `流式`, `失败`, and `HTTP 502`. Mount as a user and assert provider name, upstream model, provider filter, and provider metadata label are absent from both list and detail.

- [x] **Step 2: Run the frontend test and verify RED**

  Run the Task 2 command. Expected: three wide columns remain and user markup contains provider data.

- [x] **Step 3: Implement compact styles, tag cluster, and role-specific cells**

  Replace the three columns with one `request-info-tags` container of `ElTag` elements, reduce table `min-width`, remove the filter description, tighten panel/grid spacing, use auto-fitting columns, and branch model/detail metadata on `auth.isAdmin` / `hideSensitive`.

- [x] **Step 4: Verify GREEN**

  Run the Task 2 command and confirm the page behavior passes.

### Task 4: Full Verification

**Files:**
- Review all modified files; make no production changes before fresh verification.

**Interfaces:**
- All focused regressions, static checks, frontend tests, and builds must exit zero.

- [x] **Step 1: Run backend gates**

  ```bash
  uv run ruff check src tests scripts
  uv run ruff format --check src tests scripts
  uv run mypy src scripts
  uv run pytest tests/integration/audit/test_request_logs.py -q
  ```

- [x] **Step 2: Run frontend gates**

  ```bash
  npm --prefix frontend run lint
  npm --prefix frontend run typecheck
  npm --prefix frontend run test
  npm --prefix frontend run build
  ```

- [x] **Step 3: Run repository checks**

  ```bash
  git diff --check
  git status --short
  ```

- [x] **Step 4: Review the five user requirements against the final diff**

  Confirm compact search layout, friendly selectors, provider privacy, API-key names, and the consolidated tag column each have an automated regression assertion or direct API-contract assertion.
