# Authentication Hardening Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct token-revocation precision, make authentication rate limiting trustworthy and replica-safe, complete the administrator TOTP reset flow, and restore all CI checks.

**Architecture:** Persist microsecond token cutoffs and authentication rate-limit counters in MySQL so every gateway replica observes the same state. Treat the ASGI client address as authoritative after Uvicorn's trusted proxy processing, and pass the current administrator's TOTP state into the user editor so password reset payloads can include the step-up code.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async/MySQL 8.4, Alembic, PyJWT, Vue 3, TypeScript, Vitest, pytest.

## Global Constraints

- Preserve the existing public login, registration, refresh, and admin-user endpoint paths.
- Keep refresh responses as `TokenPair` and rotate both browser tokens atomically.
- Do not trust raw forwarding headers in application code.
- Do not commit changes; leave the completed patch for user review.

---

### Task 1: Precise token revocation

**Files:**
- Modify: `src/ai_gateway/core/security.py`
- Modify: `src/ai_gateway/auth/dependencies.py`
- Modify: `src/ai_gateway/auth/service.py`
- Modify: `src/ai_gateway/db/models/identity.py`
- Modify: `migrations/versions/0012_add_token_invalidation.py`
- Test: `tests/unit/auth/test_security.py`
- Test: `tests/integration/auth/test_login_totp.py`

**Interfaces:**
- Produces: `token_issued_at(claims: Mapping[str, Any]) -> datetime`, using a microsecond claim when present and an intentionally conservative fallback for older JWTs.
- Produces: MySQL `DATETIME(6)` storage for `User.tokens_invalidated_before`.

- [ ] **Step 1: Write failing tests for same-second ordering**

```python
def test_token_issued_at_preserves_microseconds(settings: Settings) -> None:
    token = issue_access_token(user_id=7, settings=settings)
    claims = decode_token(token, expected_type="access", settings=settings)
    assert token_issued_at(claims).microsecond != 0
```

- [ ] **Step 2: Run the focused security tests and confirm the new assertion fails**

Run: `uv run pytest tests/unit/auth/test_security.py -q`

- [ ] **Step 3: Add a private microsecond JWT claim and centralize UTC claim conversion**

```python
claims = {
    "iat": issued_at,
    "iat_us": int(issued_at.timestamp() * 1_000_000),
}
```

- [ ] **Step 4: Store cutoffs with `mysql.DATETIME(fsp=6)` and use the centralized comparison in access and refresh validation**

- [ ] **Step 5: Run unit and integration authentication tests**

Run: `GATEWAY_TEST_DATABASE_URL=mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test uv run pytest tests/unit/auth/test_security.py tests/integration/auth -q`

### Task 2: Shared, trusted authentication rate limiting

**Files:**
- Modify: `src/ai_gateway/core/rate_limit.py`
- Modify: `src/ai_gateway/auth/router.py`
- Modify: `src/ai_gateway/db/models/identity.py`
- Modify: `src/ai_gateway/db/models/__init__.py`
- Modify: `migrations/versions/0012_add_token_invalidation.py`
- Test: `tests/unit/core/test_rate_limit.py`
- Test: `tests/integration/auth/test_login_totp.py`

**Interfaces:**
- Produces: `check_rate_limit(request: Request, session: AsyncSession, *, max_requests: int, window_seconds: int, code: str, message: str) -> None`.
- Produces: `AuthRateLimit` rows keyed by the trusted ASGI client address and shared by login and registration.

- [ ] **Step 1: Write failing tests proving spoofed forwarding headers do not change the key and six attempts are rejected**

```python
request = Request({"type": "http", "client": ("203.0.113.4", 1234), "headers": [(b"x-forwarded-for", b"198.51.100.9")]})
assert client_ip(request) == "203.0.113.4"
```

- [ ] **Step 2: Run the focused rate-limit tests and confirm failure against the in-memory implementation**

Run: `uv run pytest tests/unit/core/test_rate_limit.py -q`

- [ ] **Step 3: Replace module-local buckets with a row-locked MySQL counter and commit the counter before authentication continues**

- [ ] **Step 4: Update login and registration handlers to await the database-backed check**

- [ ] **Step 5: Run rate-limit and authentication integration tests**

Run: `GATEWAY_TEST_DATABASE_URL=mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test uv run pytest tests/unit/core/test_rate_limit.py tests/integration/auth -q`

### Task 3: Administrator TOTP password-reset UI

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/users/UserFormDrawer.vue`
- Modify: `frontend/src/views/UsersView.vue`
- Test: `frontend/tests/users.spec.ts`

**Interfaces:**
- Produces: optional `UserUpdate.admin_totp_code`.
- Consumes: `CurrentUser.totp_enabled` to require a six-digit code only when a password is being reset by a TOTP-enabled administrator.

- [ ] **Step 1: Write a failing component test for submitting password plus administrator TOTP code**

```typescript
expect(onSubmit).toHaveBeenCalledWith({
  password: 'new-user-password',
  admin_totp_code: '123456',
})
```

- [ ] **Step 2: Run the focused component test and confirm the TOTP field is absent**

Run: `npm test -- tests/users.spec.ts`

- [ ] **Step 3: Add the typed field, conditional input, validation, and secret cleanup**

- [ ] **Step 4: Pass `auth.user?.totp_enabled` from `UsersView` and add the validation-field label**

- [ ] **Step 5: Run user and authentication frontend tests**

Run: `npm test -- tests/users.spec.ts tests/auth-store.spec.ts`

### Task 4: Refresh consumers and quality gates

**Files:**
- Modify: `tests/e2e/test_gateway.py`
- Format: `src/ai_gateway/auth/dependencies.py`
- Format: `src/ai_gateway/auth/service.py`

**Interfaces:**
- Consumes: refresh response `access_token` for all subsequent authenticated E2E requests.

- [ ] **Step 1: Update the E2E flow to replace its authorization header with the refreshed access token**

```python
admin_headers = {"Authorization": f"Bearer {refresh.json()['access_token']}"}
```

- [ ] **Step 2: Run the full backend suite with the isolated MySQL test database**

Run: `GATEWAY_TEST_DATABASE_URL=mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test uv run pytest -q`

- [ ] **Step 3: Run backend lint, formatting, and strict type checking**

Run: `uv run ruff check src tests scripts && uv run ruff format --check src tests scripts && uv run mypy src scripts`

- [ ] **Step 4: Run the complete frontend quality suite**

Run: `npm run lint && npm run typecheck && npm test && npm run build`
