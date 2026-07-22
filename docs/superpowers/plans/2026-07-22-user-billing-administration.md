# User Billing Administration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add exact-decimal user administration, balance adjustment, total-spend visibility, and immutable ledger inspection to the Chinese admin console.

**Architecture:** Extend the existing user response with the account aggregate and keep CRUD in `admin/users.py`, while consuming the already-existing billing adjustment and ledger endpoints from a focused frontend API module. The Vue view owns list state, per-user operation exclusion, session-bound saves, and abort controllers; focused form/dialog/drawer components own transient input, validation, and safe presentation.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, MySQL Decimal, pytest, Vue 3 Composition API, TypeScript, Element Plus, Axios, MSW, Vitest.

## Global Constraints

- Every monetary value remains a decimal string in TypeScript and is never converted through JavaScript floating point.
- An adjustment must be a signed non-zero plain decimal with no more than 8 fractional digits.
- Generate `console-${crypto.randomUUID()}` once per balance-dialog session and reuse it for retries.
- Omit a blank edit password and clear password/reason/adjustment text on close and unmount.
- Prevent self-disable/self-delete in the UI and enforce the restriction authoritatively in the backend.
- Render ledger metadata through Vue text interpolation only; never use `v-html`.
- Lock open form surfaces while saving, bind responses to their opening session, abort or ignore stale loads, register controllers before confirmation prompts, and exclude concurrent per-user operations.
- Use Chinese UI copy, local imports, and a lazy-loaded users route.

---

### Task 1: Backend total spend and self-protection

**Files:**
- Modify: `tests/integration/admin/test_users.py`
- Modify: `src/ai_gateway/admin/users.py`

**Interfaces:**
- Consumes: `User.account.total_spent: Decimal` and authenticated `AdminUser`.
- Produces: `UserResponse.total_spent: Decimal`, `self_disable_forbidden`, and `self_delete_forbidden` API errors.

- [ ] Add create/list/get assertions that parse `balance` and `total_spent` with `Decimal`, seed a `LedgerEntry(kind=usage)` plus an exact `Account.total_spent`, and assert the list response preserves `1.25000000` exactly.
- [ ] Add integration cases proving a signed-in administrator cannot disable or delete their own record.
- [ ] Run `GATEWAY_TEST_DATABASE_URL=mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test uv run pytest tests/integration/admin/test_users.py -q` and capture the missing-field/self-protection RED failures.
- [ ] Add `total_spent` to `UserResponse`, populate it in `_user_response`, and reject self-disable/self-delete before mutation.
- [ ] Rerun the focused backend command and capture GREEN.

### Task 2: Frontend behavior coverage

**Files:**
- Create: `frontend/tests/users.spec.ts`

**Interfaces:**
- Consumes: `UsersView`, `UserFormDrawer`, `BalanceDialog`, `LedgerDrawer`, `/admin/users` endpoints, and Pinia auth state.
- Produces: executable coverage for exact money, blank edit passwords, idempotency retries, safe ledger metadata, self protection, and stale/lifecycle behavior.

- [ ] Add a lazy-route test and CRUD/list rendering fixtures whose balances include exact large and fractional decimal strings.
- [ ] Add form tests proving create sends `initial_balance` as text, edit omits blank password, and sensitive form state clears on close.
- [ ] Add adjustment tests proving signed-zero/exponent rejection, exact decimal payload preservation, a `console-` key reused after failure, and a new key after reopening.
- [ ] Add ledger tests proving descending entries and hostile metadata render as text without injected elements.
- [ ] Add UI self-protection and save-lock/stale-response cases.
- [ ] Run `npm --prefix frontend run test -- users.spec.ts` and capture the missing-module RED failure.

### Task 3: Frontend API and types

**Files:**
- Create: `frontend/src/api/users.ts`
- Modify: `frontend/src/api/types.ts`

**Interfaces:**
- Consumes: `apiClient`, existing billing response types, and optional `AbortSignal`.
- Produces: `listUsers`, `createUser`, `updateUser`, `deleteUser`, `adjustBalance`, and `listLedger`.

- [ ] Add `total_spent: string` to `UserResponse`.
- [ ] Implement all six API functions with optional abort signals and no numeric coercion.
- [ ] Keep idempotency generation out of the API function so dialog-session ownership remains explicit.

### Task 4: User form, balance adjustment, and ledger components

**Files:**
- Create: `frontend/src/components/users/UserFormDrawer.vue`
- Create: `frontend/src/components/users/BalanceDialog.vue`
- Create: `frontend/src/components/users/LedgerDrawer.vue`

**Interfaces:**
- Consumes: user and ledger response types plus parent-owned `submitting/loading` flags.
- Produces: validated `UserCreate | UserUpdate`, exact `BalanceAdjustmentCreate`, and safe immutable ledger presentation.

- [ ] Build the user drawer with required create password, optional edit password, exact-string initial balance validation, self-disable controls, close locking, and transient password clearing.
- [ ] Build the balance dialog with one idempotency key generated on open, exact signed non-zero decimal validation, direction preview, retry-key reuse, close locking, and transient clearing.
- [ ] Build the ledger drawer with abort-aware parent loading, descending immutable rows, request IDs, timestamps, and `JSON.stringify` metadata rendered by interpolation.

### Task 5: Users view and route

**Files:**
- Create: `frontend/src/views/UsersView.vue`
- Modify: `frontend/src/router/index.ts`

**Interfaces:**
- Consumes: auth store user ID, user API functions, and the three user components.
- Produces: the `/users` management page and lazy route.

- [ ] Implement the Chinese table with email, role, active state, exact balance, exact total spent, timestamps, search, loading/error/empty states, and actions.
- [ ] Add per-user operation exclusion and register operation controllers before delete confirmation.
- [ ] Session-bind form/adjustment responses, lock surfaces while saving, abort stale list/ledger/save requests, and ignore generation/revision-stale responses.
- [ ] Disable edit-deactivation and delete for the signed-in administrator while retaining backend error handling.
- [ ] Point the existing lazy users route at `UsersView.vue`.
- [ ] Run the focused frontend test and capture GREEN.

### Task 6: Verification, review, report, and commit

**Files:**
- Create: `.superpowers/sdd/task-8-report.md`

**Interfaces:**
- Consumes: all Task 8 code and tests.
- Produces: verified commit plus RED/GREEN and quality-gate evidence.

- [ ] Run focused and full backend pytest, Ruff check/format-check, and strict mypy with the configured test database URL where needed.
- [ ] Run focused and full frontend Vitest, lint, typecheck, and production build.
- [ ] Review the diff for exact-money conversions, idempotency lifecycle, sensitive state clearing, self-protection, safe metadata, stale responses, and operation exclusion.
- [ ] Write `.superpowers/sdd/task-8-report.md` with commands, outcomes, evidence, and concerns.
- [ ] Commit the scoped Task 8 files with `feat: add user billing administration`.
