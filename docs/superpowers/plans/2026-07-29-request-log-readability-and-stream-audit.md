# Request Log Readability and Stream Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace opaque request-log IDs with readable catalog identities and store Claude/OpenAI/Gemini SSE response previews as redacted structured events with an explicit usage summary.

**Architecture:** Request-log list/detail queries will left-join the user, API key, model, provider, and model-route tables and project stable display fields without loading audit blobs. The audit service will recognize `text/event-stream`, parse its captured preview with the gateway SSE decoder, redact each decoded payload, and add the finalized token/cache usage to the response detail metadata. The Vue list and drawer will render the new labels while retaining internal IDs only for filtering and detail lookup.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, MySQL, pytest, Vue 3, TypeScript, Vitest.

## Global Constraints

- Preserve all existing uncommitted provider-route and Claude protocol changes.
- Do not expose API-key hashes, credentials, authorization headers, or unredacted SSE payload secrets.
- Keep request IDs in API responses for cursor/detail operations, but do not show them as a list column.
- Existing logs whose related records are absent must render explicit fallback labels.
- Audit detail size remains bounded by `audit_body_limit_bytes`.

---

### Task 1: Project Readable Request-Log Identities

**Files:**
- Modify: `src/ai_gateway/admin/request_logs.py`
- Modify: `src/ai_gateway/user/request_logs.py`
- Test: `tests/integration/audit/test_request_logs.py`

**Interfaces:**
- Admin `RequestLogSummary` adds `user_email`, `api_key_prefix`, `model_name`, `provider_name`, and `route_upstream_model`.
- User `RequestLogSummary` adds all of the same fields except `user_email`.
- Related fields are nullable except the admin user email.

- [ ] **Step 1: Write failing API projection tests**

  Extend the admin list/detail test and add a user list/detail assertion with literal expected values:

  ```python
  assert item["user_email"] == "audit-member@example.com"
  assert item["api_key_prefix"] == "sk-gw-audit-"
  assert item["model_name"] == "audit-model"
  assert item["provider_name"] == "audit-provider"
  assert item["route_upstream_model"] == "provider-audit-model"
  ```

- [ ] **Step 2: Verify RED**

  Run:

  ```bash
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/integration/audit/test_request_logs.py -q
  ```

  Expected: response assertions fail because the readable fields do not exist.

- [ ] **Step 3: Implement joined summary projections**

  Add labeled joined columns and reuse the same select for list and detail endpoints:

  ```python
  _IDENTITY_COLUMNS = (
      User.email.label("user_email"),
      ApiKey.key_prefix.label("api_key_prefix"),
      Model.canonical_name.label("model_name"),
      Provider.name.label("provider_name"),
      ModelRoute.upstream_model.label("route_upstream_model"),
  )
  ```

  Use outer joins for optional/deleted related records. Keep blob columns out of list queries.

- [ ] **Step 4: Verify GREEN**

  Run the Task 1 focused command and confirm it passes.

### Task 2: Structure SSE Audit Details and Persist Usage Metadata

**Files:**
- Modify: `src/ai_gateway/audit/service.py`
- Test: `tests/integration/audit/test_request_logs.py`

**Interfaces:**
- A response with `Content-Type: text/event-stream` stores `body.format == "sse"`, `body.events`, `body.event_count`, and `body.byte_length`.
- Every completed/failed response detail stores `usage.input_tokens`, `usage.output_tokens`, `usage.cache_read_tokens`, `usage.cache_write_tokens`, and `usage.source`.

- [ ] **Step 1: Write a failing Claude SSE audit regression test**

  Complete a request with a literal Claude SSE byte sequence containing `message_start`, a text delta, `message_delta`, and `message_stop`, then assert:

  ```python
  assert detail["body"]["format"] == "sse"
  assert detail["body"]["events"][0]["data"]["type"] == "message_start"
  assert detail["usage"] == {
      "input_tokens": 32769,
      "output_tokens": 517,
      "cache_read_tokens": 12000,
      "cache_write_tokens": 8000,
      "source": "provider",
  }
  ```

  Include a secret field in an SSE payload and assert it is `[REDACTED]`.

- [ ] **Step 2: Verify RED**

  Run the Task 1 focused command. Expected: the body is currently `{unparseable, byte_length, sha256}` and has no usage object.

- [ ] **Step 3: Implement bounded SSE decoding and usage projection**

  Detect the content type case-insensitively, feed the captured bytes through `SSEDecoder`, JSON-decode each `data:` value, preserve event names/IDs/comments, and pass the result through existing recursive redaction. Merge this literal usage object into response metadata before compression:

  ```python
  response_metadata["usage"] = {
      "input_tokens": prompt_tokens,
      "output_tokens": completion_tokens,
      "cache_read_tokens": cache_read_tokens,
      "cache_write_tokens": cache_write_tokens,
      "source": usage_source.value if usage_source is not None else None,
  }
  ```

- [ ] **Step 4: Verify GREEN**

  Run the Task 1 focused command and confirm both ordinary JSON and SSE audit cases pass.

### Task 3: Render Readable Log Rows and Details

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/views/RequestLogsView.vue`
- Modify: `frontend/src/components/request-logs/RequestLogDetailDrawer.vue`
- Test: `frontend/tests/request-logs.spec.ts`

**Interfaces:**
- List columns no longer include request UUID.
- Admin identity renders `user_email` plus `api_key_prefix`; user identity renders only the prefix.
- Catalog identity renders model name, provider name, and upstream model on readable lines.

- [ ] **Step 1: Write failing component tests**

  Change fixtures to include readable identity fields and assert the row contains:

  ```typescript
  expect(row.text()).toContain('audit-member@example.com')
  expect(row.text()).toContain('sk-gw-audit-…')
  expect(row.text()).toContain('audit-model')
  expect(row.text()).toContain('audit-provider')
  expect(row.text()).toContain('provider-audit-model')
  expect(row.text()).not.toContain(firstLog.id)
  ```

  Assert the `请求 ID` table heading and numeric entity labels are absent.

- [ ] **Step 2: Verify RED**

  Run:

  ```bash
  npm --prefix frontend run test -- request-logs.spec.ts
  ```

- [ ] **Step 3: Update types, list layout, and drawer metadata**

  Add the new API fields, remove the UUID column, render prefixes with an ellipsis, and use explicit fallbacks such as `已删除路由` when joined data is null. Keep `log.id` only as the Vue key and detail request argument.

- [ ] **Step 4: Verify GREEN**

  Run the Task 3 focused command and confirm it passes.

### Task 4: Full Verification

**Files:**
- Review all modified files and preserve unrelated working-tree changes.

- [ ] **Step 1: Run backend quality gates**

  ```bash
  uv run ruff check src tests scripts
  uv run ruff format --check src tests scripts
  uv run mypy src scripts
  GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest -W error --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90
  ```

- [ ] **Step 2: Run frontend quality gates**

  ```bash
  npm --prefix frontend run lint
  npm --prefix frontend run typecheck
  npm --prefix frontend run test
  npm --prefix frontend run build
  ```

- [ ] **Step 3: Run repository and container gates**

  ```bash
  docker compose config --quiet
  docker build -t lean-ai-gateway:test .
  git diff --check
  ```
