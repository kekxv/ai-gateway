# Custom TOTP Secret Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an authenticated user optionally supply a strong Base32 TOTP secret from Security settings, with an explicit risk warning and the existing verify-before-activate enrollment guarantees.

**Architecture:** Extend the existing `POST /auth/totp/setup` request with an optional `custom_secret`. Normalize and validate it in the shared security layer, store it only as the encrypted pending secret, and keep the current secret active until `/auth/totp/confirm` succeeds. Add an opt-in custom-secret panel to the Vue security page; it validates locally, requires explicit warning acknowledgement, sends the secret only to setup, and erases it on every terminal lifecycle path.

**Tech Stack:** FastAPI, Pydantic v2, PyOTP, SQLAlchemy async, Vue 3, Pinia, Element Plus, Vitest/MSW, pytest/MySQL.

## Global Constraints

- A custom secret must normalize to unpadded RFC 4648 Base32 and decode to at least 20 bytes (160 bits).
- The normalized secret is limited to 128 Base32 characters.
- Invalid custom secrets return `422 invalid_totp_secret` without echoing secret material.
- Starting setup may replace only `pending_totp_secret_encrypted`; an active TOTP secret remains unchanged until confirmation succeeds.
- Existing generated-secret setup and current-code requirements for re-enrollment remain unchanged.
- The browser must not place the custom secret in storage, logs, notices, URLs, screenshots, or persistent component state after setup begins, is cancelled, logout occurs, or the component unmounts.
- The custom-secret control must display a warning that weak, reused, or lost secrets can compromise or lock the account, and require acknowledgement before submission.

---

### Task 1: Shared TOTP secret validation and setup contract

**Files:**
- Modify: `src/ai_gateway/core/security.py`
- Modify: `src/ai_gateway/admin/bootstrap.py`
- Modify: `src/ai_gateway/auth/schemas.py`
- Modify: `src/ai_gateway/auth/router.py`
- Test: `tests/unit/auth/test_security.py`
- Test: `tests/integration/auth/test_login_totp.py`

**Interfaces:**
- Produces: `validate_totp_secret(secret: str) -> str`.
- Produces: `TotpSetupRequest.custom_secret: SecretStr | None`.
- Consumes: existing pending-secret encryption and `/auth/totp/confirm` activation flow.

- [ ] **Step 1: Write failing validator tests**

Add literal tests proving formatted lowercase Base32 normalizes to uppercase without separators, malformed/short/empty values raise `ValueError`, and a 129-character value is rejected.

- [ ] **Step 2: Run validator tests and verify RED**

Run: `uv run pytest -q tests/unit/auth/test_security.py`

Expected: collection or assertion failure because `validate_totp_secret` does not exist.

- [ ] **Step 3: Implement the shared validator and reuse it for bootstrap**

Normalize ASCII whitespace and hyphens, uppercase the value, reject non-`A-Z2-7` data, decode with Base32 padding, enforce 20 decoded bytes and 128 encoded characters, then return the unpadded normalized value. Replace the private bootstrap validator with the shared function.

- [ ] **Step 4: Run validator tests and verify GREEN**

Run: `uv run pytest -q tests/unit/auth/test_security.py tests/integration/test_create_admin.py`

- [ ] **Step 5: Write failing setup endpoint tests**

Add integration cases that submit a known 32-character secret, assert the URI contains that normalized secret, assert only encrypted pending state changes, and confirm it with a real PyOTP code. Add malformed and too-short cases that assert `422 invalid_totp_secret`, no plaintext echo, and no pending-state mutation. Add a re-enrollment case proving the current code is still required when `custom_secret` is supplied.

- [ ] **Step 6: Run endpoint tests and verify RED**

Run: `uv run pytest -q tests/integration/auth/test_login_totp.py -k 'custom_secret'`

Expected: failure because setup ignores or forbids `custom_secret`.

- [ ] **Step 7: Extend setup schema and route**

Add `custom_secret` to `TotpSetupRequest`. After locking and validating any active current TOTP code, call `validate_totp_secret`; translate `ValueError` to `422 invalid_totp_secret`; otherwise generate a secret as before. Encrypt only the validated/generated pending secret and return the provisioning URI.

- [ ] **Step 8: Run auth regression tests and commit**

Run: `uv run pytest -q tests/unit/auth/test_security.py tests/integration/auth/test_login_totp.py tests/integration/test_create_admin.py`

Commit: `feat: accept validated custom totp secrets`

---

### Task 2: Warning-gated custom-secret security UI

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/views/SecurityView.vue`
- Test: `frontend/tests/security.spec.ts`

**Interfaces:**
- Consumes: `TotpSetupRequest.custom_secret?: string | null`.
- Produces: `data-test="use-custom-totp-secret"`, `custom-totp-secret`, `custom-totp-warning`, and `custom-totp-acknowledged` controls.

- [ ] **Step 1: Write failing warning and payload tests**

Mount the real security view and assert opting into a custom secret reveals a warning about weak/reused/lost secrets, a masked secret field, and acknowledgement. Assert malformed or short secrets do not send a request; a normalized 32-character Base32 value plus acknowledgement sends `{custom_secret: ...}` (and the current code during re-enrollment), then immediately clears the input.

- [ ] **Step 2: Run security tests and verify RED**

Run: `npm test -- tests/security.spec.ts`

Expected: selectors are absent and setup payload has no custom secret.

- [ ] **Step 3: Implement role-independent custom-secret controls**

Add opt-in state, normalization, local validation, warning copy, acknowledgement gating, and payload construction. Keep generated setup as the default. Never render the secret back into notices or the provisioning URI input beyond the server-owned URI already required by TOTP enrollment.

- [ ] **Step 4: Write failing lifecycle-erasure assertions**

Extend cancellation/logout/unmount and delayed-response tests to assert the custom secret and acknowledgement are reset and cannot be restored by a stale response.

- [ ] **Step 5: Implement lifecycle erasure and error mapping**

Clear custom secret state from `eraseSecrets`/invalidation and map `invalid_totp_secret` to the custom-secret field without displaying the server message.

- [ ] **Step 6: Run frontend regression tests and commit**

Run: `npm test -- tests/security.spec.ts tests/auth-store.spec.ts tests/router.spec.ts`

Run: `npm run lint && npm run typecheck`

Commit: `feat: add warned custom totp setup controls`

---

### Task 3: Documentation and complete verification

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`

**Interfaces:**
- Documents: generated secrets remain recommended; custom secrets must be random Base32 with at least 160 bits and require secure backup.

- [ ] **Step 1: Update user-facing documentation**

Document the custom-secret option, its 160-bit minimum, and the weak/reused/lost-secret warning. State that activation still requires a code from the new secret.

- [ ] **Step 2: Run complete verification**

Run backend Ruff, formatting, mypy, and the full pytest coverage command against disposable MySQL. Run all frontend Vitest tests, ESLint, type-check, and production build. Validate root/example Compose files and run `git diff --check`.

- [ ] **Step 3: Commit documentation and verification adjustments**

Commit: `docs: explain custom totp secret safety`

