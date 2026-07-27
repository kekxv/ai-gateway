# Anthropic Base URL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated `/anthropic` public API namespace that works as an Anthropic SDK base URL while preserving every existing gateway endpoint.

**Architecture:** Register alias routes that reuse the existing Claude message handler and canonical gateway service. Add dedicated Anthropic model-list and model-detail handlers so protocol selection comes from the URL instead of the `anthropic-version` header, while retaining the legacy header-dispatched `/v1/models` route.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy asyncio, httpx, pytest.

## Global Constraints

- Keep `POST /v1/messages` operational and behavior-compatible.
- Keep `GET /v1/models` header dispatch operational for existing OpenAI and Anthropic clients.
- The recommended Anthropic SDK base URL is the gateway origin plus `/anthropic`; the SDK appends `/v1/messages` or `/v1/models`.
- Dedicated Anthropic routes must always return Anthropic-native success and error shapes, even when `anthropic-version` is absent.
- Reuse existing authentication, scope filtering, routing, billing, audit, and protocol conversion logic.

---

### Task 1: Add dedicated Anthropic message and model routes

**Files:**
- Modify: `tests/unit/gateway/test_protocol_error_routing.py`
- Modify: `tests/contract/gateway/test_models.py`
- Modify: `src/ai_gateway/gateway/claude.py`
- Modify: `src/ai_gateway/gateway/models.py`

**Interfaces:**
- Produces: `POST /anthropic/v1/messages` using `GatewayService.handle(request, Protocol.CLAUDE)`.
- Produces: `GET /anthropic/v1/models` and `GET /anthropic/v1/models/{model_id}` using Claude route eligibility and Anthropic-native payloads.

- [ ] **Step 1: Write failing message-route tests**

Add `/anthropic/v1/messages` to the real `create_app()` runtime-error matrix and assert database, timeout, and unexpected failures use the Claude error envelope. The test must fail with 404 before the route exists.

- [ ] **Step 2: Write failing model-route tests**

Create Claude and OpenAI routes in the test catalog, call `/anthropic/v1/models` without `anthropic-version`, and assert only the Claude model is returned in Claude shape. Call `/anthropic/v1/models/{id}` for an alias and canonical ID, and assert unknown or OpenAI-only IDs return Claude `model_not_found` errors.

- [ ] **Step 3: Run the focused tests and verify the missing routes fail**

Run: `GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/unit/gateway/test_protocol_error_routing.py tests/contract/gateway/test_models.py -q`

- [ ] **Step 4: Implement the minimal route aliases and dedicated handlers**

Stack `/anthropic/v1/messages` on the existing Claude message function. In `models.py`, authenticate normally, call `_list_selectable_models(..., Protocol.CLAUDE)`, format with `_claude_model`, and use `native_error_response(Protocol.CLAUDE, exc)` for every dedicated-route failure.

- [ ] **Step 5: Run the focused tests and verify they pass**

Run: `GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/unit/gateway/test_protocol_error_routing.py tests/contract/gateway/test_models.py -q`

### Task 2: Document SDK-compatible base URLs and backward compatibility

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/protocol-compatibility.md`

**Interfaces:**
- Produces: user-facing configuration examples for `ANTHROPIC_BASE_URL` and explicit legacy-route guarantees.

- [ ] **Step 1: Update endpoint tables and examples**

List `/anthropic/v1/messages` and `/anthropic/v1/models` as recommended Anthropic endpoints, retain `/v1/messages` as a legacy-compatible alias, and change Anthropic curl examples to use `$GATEWAY_URL/anthropic/v1/messages`.

- [ ] **Step 2: Add SDK configuration examples**

Document `ANTHROPIC_BASE_URL="$GATEWAY_URL/anthropic"` and state that the SDK appends `/v1/messages`. Explain that upstream provider protocol rows already have their own `base_url` and are unaffected.

- [ ] **Step 3: Update protocol compatibility routing notes**

Document that the dedicated path determines Claude model/error format without header inspection, while legacy `/v1/models` continues using `anthropic-version` for backward compatibility.

### Task 3: Verify and commit the isolated branch

**Files:**
- Test: repository-wide Python tests and static checks.

**Interfaces:**
- Produces: a clean feature branch commit ready for review or merge.

- [ ] **Step 1: Run focused gateway tests**

Run: `GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest tests/contract/gateway tests/unit/gateway -q`

- [ ] **Step 2: Run repository verification**

Run: `uv run ruff check .`

Run: `uv run mypy`

Run: `GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest -q`

- [ ] **Step 3: Check and commit the exact diff**

```bash
git diff --check
git status --short
git add README.md README.zh-CN.md docs/protocol-compatibility.md docs/superpowers/plans/2026-07-27-anthropic-base-url.md src/ai_gateway/gateway/claude.py src/ai_gateway/gateway/models.py tests/contract/gateway/test_models.py tests/unit/gateway/test_protocol_error_routing.py
git commit -m "feat: add dedicated Anthropic base URL"
```
