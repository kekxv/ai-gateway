# MySQL Pool Exhaustion Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent gateway HTTP and WebSocket traffic from holding MySQL connections across upstream I/O, make request-session cleanup cancellation-safe, and expose bounded pool tuning settings.

**Architecture:** Gateway request sessions remain responsible for short authentication, catalog, routing, and provider reads, but explicitly release their connection before billing, audit, upstream HTTP, streaming, or WebSocket relay work. Application session finalization runs inside an AnyIO shield so a client disconnect cannot interrupt SQLAlchemy connection return. The shared application engine keeps bounded QueuePool behavior with operator-configurable size, overflow, checkout timeout, and recycle interval.

**Tech Stack:** Python 3.12, FastAPI/Starlette, AnyIO, SQLAlchemy 2 async engine, asyncmy, MySQL 8.4, pytest.

## Global Constraints

- Preserve the existing six uncommitted CI fixes and all tiered dual-pricing behavior.
- Never hold a request-scoped database connection while waiting for an upstream HTTP response, SSE stream, or WebSocket relay.
- Loaded model tiers and provider multiplier values must remain usable after the read session is closed.
- Billing, audit, route-health, and recovery services continue using their existing independently owned short-lived sessions.
- Pool growth stays bounded and configurable; tuning must not replace connection-lifecycle fixes.
- Cancellation-safe close must preserve the caller's cancellation after the connection has been returned.

---

### Task 1: Release Gateway Read Connections Before External Work

**Files:**
- Modify: `src/ai_gateway/gateway/service.py`
- Modify: `src/ai_gateway/gateway/websocket.py`
- Test: `tests/integration/gateway/test_pool_lifecycle.py`
- Test: `tests/contract/gateway/test_non_streaming.py`
- Test: `tests/contract/gateway/test_websocket.py`

**Interfaces:**
- Produces: `_release_read_session(session: AsyncSession) -> None`, which closes only real SQLAlchemy request sessions after all required ORM fields have been eagerly loaded.
- Consumes: existing `BillingService`, `AuditService`, `Router`, `Model.price_tiers`, and provider multiplier fields.

- [x] **Step 1: Write a failing MySQL pool-size-one integration test**

  Create a real `AsyncEngine` against the disposable test database with `pool_size=1`, `max_overflow=0`, and a short `pool_timeout`. Build one authenticated non-streaming gateway request using the real `BillingService` and assert it completes instead of timing out while reserving or settling.

- [x] **Step 2: Verify RED**

  Run `GATEWAY_TEST_DATABASE_URL=... uv run pytest tests/integration/gateway/test_pool_lifecycle.py -q` and confirm the request fails at pool checkout because the read session owns the only connection when billing starts.

- [x] **Step 3: Implement minimal HTTP and WebSocket release points**

  Close the read session after initial model/routing price reads, after every route selection before HTTP send, and immediately after provider/model snapshots used by settlement or WebSocket relay. Do not close fake sessions used by protocol contract tests.

- [x] **Step 4: Verify GREEN and gateway regressions**

  Run the new integration test plus non-streaming, streaming, WebSocket, failover, disconnect, and WebSocket billing suites.

### Task 2: Make Pool Limits Explicit and Session Close Cancellation-Safe

**Files:**
- Modify: `src/ai_gateway/core/config.py`
- Modify: `src/ai_gateway/db/session.py`
- Modify: `src/ai_gateway/main.py`
- Test: `tests/unit/db/test_session.py`
- Test: `tests/integration/test_startup.py`

**Interfaces:**
- Produces settings `database_pool_size`, `database_max_overflow`, `database_pool_timeout_seconds`, and `database_pool_recycle_seconds`.
- Produces `get_engine_for_url(..., pool_size, max_overflow, pool_timeout, pool_recycle)` with `pool_pre_ping=True`.
- Produces `close_session_shielded(session: AsyncSession) -> None` for FastAPI dependency finalization.

- [x] **Step 1: Write failing engine-configuration and cancellation tests**

  Capture `create_async_engine` arguments and assert all bounded pool settings are forwarded. Cancel an outer AnyIO scope during a fake session close and assert close completes exactly once before cancellation exits.

- [x] **Step 2: Verify RED**

  Run `uv run pytest tests/unit/db/test_session.py tests/integration/test_startup.py -q` and confirm the new interfaces/settings do not exist.

- [x] **Step 3: Implement bounded defaults and shielded finalization**

  Default to pool size 20, overflow 20, timeout 30 seconds, and recycle 1800 seconds. Pass settings into both configured and lifespan-created engines. Replace the production app dependency's unshielded `async with session_factory()` cleanup with explicit shielded close.

- [x] **Step 4: Verify GREEN**

  Run the Task 2 command and the database safety/schema suites.

### Task 3: Operator Documentation and CI-Order Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `README.zh-CN.md`

**Interfaces:**
- Documents: bounded pool settings, total possible application connections per process, and the operational distinction between checkout timeout and MySQL availability.

- [x] **Step 1: Document the four environment variables**

  Add exact defaults and advise sizing MySQL `max_connections` above `workers * (pool_size + max_overflow)` plus operational headroom.

- [x] **Step 2: Run Python CI gates**

  Run Ruff check, Ruff format check, mypy, then full pytest with warnings-as-errors and 90% coverage.

- [x] **Step 3: Run frontend and repository gates**

  Run frontend lint/typecheck/test/build, Playwright E2E, both Compose validations, Docker build, `git diff --check`, and inspect final status.
