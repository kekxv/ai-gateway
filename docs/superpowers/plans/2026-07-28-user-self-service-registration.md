# User Self-Service Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add public registration with an exactly-once first administrator, authenticated password and TOTP management for every user, and a bootstrap-free example deployment.

**Architecture:** Serialize registrations with a singleton database lock row inside the same transaction that creates the user and zero-balance account; the first committed user receives `admin`, and later users receive `user`. Keep administrator APIs protected, but allow every authenticated user into a role-aware console whose security page supports password change plus TOTP enrollment, replacement, and disable. Preserve the optional bootstrap script for production automation while changing the disposable example to initialize through the registration page.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, MySQL 8.4, Alembic, Argon2, PyOTP, Vue 3, Pinia, Vue Router, Element Plus, Vitest/MSW, Playwright.

## Global Constraints

- Public registration is enabled without bootstrap administrator environment variables.
- The first committed registered user is the only registration-created administrator; every later registered user has role `user`.
- A registered user and its zero-balance account are created atomically, including under concurrent first registrations.
- Password changes require the current password and never return or persist plaintext credentials.
- TOTP disable requires both the current password and a valid current six-digit TOTP code, then clears active and pending encrypted secrets.
- Regular users may access only authenticated account-security UI; provider, model, user, API-key, request-log, and dashboard routes remain administrator-only.
- Existing optional `GATEWAY_BOOTSTRAP_ADMIN_*` automation remains supported by the root Compose deployment.
- The `example/` deployment contains no built-in administrator email, password, or TOTP secret.

---

### Task 1: Transaction-safe public registration

**Files:**
- Create: `alembic/versions/0010_add_registration_lock.py`
- Modify: `src/ai_gateway/main.py`
- Modify: `src/ai_gateway/db/models/identity.py`
- Modify: `src/ai_gateway/db/models/__init__.py`
- Modify: `src/ai_gateway/auth/schemas.py`
- Modify: `src/ai_gateway/auth/service.py`
- Modify: `src/ai_gateway/auth/router.py`
- Test: `tests/integration/auth/test_registration.py`
- Test: `tests/integration/test_concurrency.py`
- Test: `tests/integration/test_schema.py`

**Interfaces:**
- Consumes: `AsyncSession`, `User`, `Account`, `hash_password()`, token issuers.
- Produces: `POST /auth/register`, `RegisterRequest`, and `register_user(*, session, email, password) -> User`.

- [ ] **Step 1: Write failing endpoint tests for first and later registration**

Create integration cases that submit literal payloads to `/auth/register` and assert:

```python
assert first.status_code == 201
assert first.json()["access_token"]
assert stored_first.role == "admin"
assert stored_first.account.balance == Decimal("0.00000000")

assert second.status_code == 201
assert stored_second.role == "user"
```

Also assert duplicate email returns `409/email_exists`, malformed or short credentials return 422 without echoing the password, and login works with the registered credentials.

- [ ] **Step 2: Run endpoint tests and verify RED**

Run:

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' \
  uv run pytest -q tests/integration/auth/test_registration.py
```

Expected: FAIL because `/auth/register` does not exist.

- [ ] **Step 3: Write the failing concurrent-first-registration test**

Use two independent sessions from `async_sessionmaker(test_engine)` and `asyncio.gather`. Assert two distinct users are committed, exactly one role is `admin`, exactly one role is `user`, and both have accounts.

- [ ] **Step 4: Run the concurrency test and verify RED**

Run the new named test in `tests/integration/test_concurrency.py`; expect failure because `register_user` and its serialization row do not exist.

- [ ] **Step 5: Add migration and model for a singleton registration lock**

Add table `registration_locks` with integer primary key `id`. `register_user` must execute MySQL `INSERT ... ON DUPLICATE KEY UPDATE id = id`, then select `id=1 FOR UPDATE` before checking whether any user exists. Keep the lock row, user insert, and account insert in one transaction.

Set:

```python
REQUIRED_MIGRATION_HEAD = "0010"
```

and cover the table in schema/reflection tests.

- [ ] **Step 6: Implement registration schemas, service, and route**

Use these contracts:

```python
class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=8, max_length=1024)

async def register_user(*, session: AsyncSession, email: str, password: str) -> User:

@router.post("/register", response_model=TokenPair, status_code=201)
async def register(
    payload: RegisterRequest,
    session: Session,
    settings: AppSettings,
) -> TokenPair:
```

Trim and lowercase the email, create `Account()` with default zero balance, map duplicate email to `409/email_exists`, commit before issuing tokens, and never include role choice in the public payload.

- [ ] **Step 7: Verify GREEN**

Run the endpoint, concurrency, schema, migration-head, login, and admin-user suites. Expect all selected tests to pass.

- [ ] **Step 8: Commit registration backend**

```bash
git add alembic/versions/0010_add_registration_lock.py src/ai_gateway tests/integration
git commit -m "feat: add transaction-safe public registration"
```

### Task 2: Self-service password change and TOTP disable APIs

**Files:**
- Modify: `src/ai_gateway/auth/schemas.py`
- Modify: `src/ai_gateway/auth/router.py`
- Modify: `src/ai_gateway/auth/service.py`
- Test: `tests/integration/auth/test_account_security.py`
- Test: `tests/integration/auth/test_login_totp.py`

**Interfaces:**
- Consumes: bearer-authenticated `CurrentUser`, Argon2 verification/hashing, encrypted TOTP secret.
- Produces: `POST /auth/password`, `POST /auth/totp/disable`, `PasswordChangeRequest`, and `TotpDisableRequest`.

- [ ] **Step 1: Write failing password-change tests**

Assert the endpoint requires authentication, rejects a wrong current password with `401/invalid_credentials`, accepts a new password of at least eight characters, invalidates the old password for login, permits the new password, and never returns either password.

- [ ] **Step 2: Write failing TOTP-disable tests**

For a TOTP-enabled user, assert wrong password and wrong code are rejected, correct credentials return `{"totp_enabled": false}`, and all three fields become:

```python
user.totp_enabled is False
user.totp_secret_encrypted is None
user.pending_totp_secret_encrypted is None
```

Assert a subsequent login no longer requires TOTP and disabling an already-disabled account returns `409/totp_not_enabled`.

- [ ] **Step 3: Run new security tests and verify RED**

Run `tests/integration/auth/test_account_security.py`; expect 404 responses for both routes.

- [ ] **Step 4: Implement row-locked credential mutations**

Add schemas:

```python
class PasswordChangeRequest(BaseModel):
    current_password: SecretStr
    new_password: SecretStr = Field(min_length=8, max_length=1024)

class TotpDisableRequest(BaseModel):
    current_password: SecretStr
    code: SecretStr = Field(min_length=6, max_length=6)
```

Both handlers reload the current user using `SELECT ... FOR UPDATE`. Password change verifies `current_password` before hashing. TOTP disable verifies the password and decrypted active TOTP secret before clearing state and committing.

- [ ] **Step 5: Verify GREEN and regress existing TOTP replacement**

Run the new file plus `tests/integration/auth/test_login_totp.py` and `tests/integration/auth/test_me.py`; expect all to pass.

- [ ] **Step 6: Commit account security APIs**

```bash
git add src/ai_gateway/auth tests/integration/auth
git commit -m "feat: add self-service account security APIs"
```

### Task 3: Registration UI and role-aware authenticated routing

**Files:**
- Create: `frontend/src/views/RegisterView.vue`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/auth.ts`
- Modify: `frontend/src/stores/auth.ts`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/views/LoginView.vue`
- Modify: `frontend/src/layouts/AdminLayout.vue`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/tests/register.spec.ts`
- Test: `frontend/tests/auth-store.spec.ts`
- Test: `frontend/tests/router.spec.ts`
- Test: `frontend/tests/login.spec.ts`
- Test: `frontend/tests/admin-layout.spec.ts`

**Interfaces:**
- Consumes: `POST /auth/register`, token pair, `/auth/me`, `CurrentUser.role`.
- Produces: public `/register`, `auth.register()`, and `meta.requiresAdmin` routing.

- [ ] **Step 1: Write failing auth-store and registration-view tests**

Assert `auth.register({email, password})` stores returned tokens, fetches `/auth/me`, accepts both `admin` and `user`, and ignores stale responses after logout. Mount `RegisterView` and assert password confirmation is local-only, secrets clear on failure/unmount, successful first-admin registration routes to dashboard, and regular registration routes to security.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
npm --prefix frontend test -- register.spec.ts auth-store.spec.ts
```

Expected: FAIL because the view and store action do not exist and regular users are rejected.

- [ ] **Step 3: Write failing router and layout role tests**

Assert unauthenticated users may visit `/register`; authenticated users are redirected away from login/register; regular users are redirected from every administrator route to `/security`; and their navigation contains only “安全设置”. Administrator navigation remains unchanged.

- [ ] **Step 4: Implement API types, store action, routes, and UI**

Add `RegisterRequest`, call `rawClient.post('/auth/register')`, and share a private token-to-current-user flow between login and register. Remove administrator rejection from authentication restore/login, retain `isAdmin`, add `requiresAdmin: true` to administrator child routes, and choose the default authenticated destination by role.

`RegisterView` must provide email, password, confirmation, “注册” submit, a login link, and copy explaining that only the first registered account becomes administrator. `LoginView` must accept all accounts and link to registration.

- [ ] **Step 5: Implement role-aware shell navigation**

Mark navigation items with `requiresAdmin`; expose the filtered list as a computed value. A regular user sees the account email, security page, and logout only. Change security copy from “管理员账户” to “账户”.

- [ ] **Step 6: Verify GREEN**

Run all five listed frontend test files and ensure each passes without Vue warnings.

- [ ] **Step 7: Commit registration and routing UI**

```bash
git add frontend/src frontend/tests
git commit -m "feat: add role-aware registration console"
```

### Task 4: Password and TOTP-disable controls in Security

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/auth.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/views/SecurityView.vue`
- Test: `frontend/tests/security.spec.ts`

**Interfaces:**
- Consumes: `POST /auth/password`, `POST /auth/totp/disable`, and `auth.refreshCurrentUser()`.
- Produces: password-change form and destructive TOTP-disable confirmation form.

- [ ] **Step 1: Write failing password UI tests**

Assert current/new/confirmation passwords are required, mismatch is rejected locally, only current and new passwords are sent, fields clear after success/failure/unmount, duplicate submits are blocked, and success text is safe.

- [ ] **Step 2: Write failing TOTP-disable UI tests**

For an enabled user, assert the page asks for current password and current six-digit code, calls `/auth/totp/disable`, refreshes `/auth/me`, changes the status to “未启用”, and clears credentials on every terminal path.

- [ ] **Step 3: Run Security tests and verify RED**

Run `npm --prefix frontend test -- security.spec.ts`; expect missing controls.

- [ ] **Step 4: Implement typed API calls and Security forms**

Add:

```ts
changePassword(payload: { current_password: string; new_password: string }): Promise<void>
disableTotp(payload: { current_password: string; code: string }): Promise<TotpConfirmResponse>
```

Keep password/TOTP secrets only in component refs, abort outstanding requests on logout/unmount, and use `autocomplete="current-password"` / `autocomplete="new-password"` appropriately.

- [ ] **Step 5: Verify GREEN and existing enrollment regression**

Run all `security.spec.ts` cases and confirm original enable/rebind tests still pass.

- [ ] **Step 6: Commit self-service UI**

```bash
git add frontend/src/api frontend/src/views/SecurityView.vue frontend/tests/security.spec.ts
git commit -m "feat: manage password and TOTP from security settings"
```

### Task 5: Bootstrap-free example, documentation, and acceptance coverage

**Files:**
- Modify: `example/compose.yaml`
- Modify: `example/README.md`
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `docs/operations.md`
- Modify: `tests/unit/test_compose_config.py`
- Modify: `frontend/e2e/admin-console.spec.ts`
- Test: `tests/integration/test_create_admin.py`

**Interfaces:**
- Consumes: migration-only setup and `/console/register` first-user flow.
- Produces: example deployment with no default administrator secret and documented optional bootstrap alternative.

- [ ] **Step 1: Rewrite Compose tests first**

Replace demo-default assertions with behavior assertions: rendered `example/compose.yaml` contains no `GATEWAY_BOOTSTRAP_ADMIN_*` environment keys or `create_admin.py` command, setup runs `alembic upgrade head`, and gateway still depends on successful setup.

- [ ] **Step 2: Run Compose tests and verify RED**

Run `uv run pytest -q tests/unit/test_compose_config.py`; expect failure on current demo credentials.

- [ ] **Step 3: Update example Compose and docs**

Make example setup migration-only. Tell users to open `/console/register`, register the first account as administrator, then use `/console/login`; remove all public default admin/TOTP values. Keep root Compose and `scripts/create_admin.py` documented as an optional non-interactive production path, explicitly state all bootstrap variables may be absent, and document later registrations as regular users.

- [ ] **Step 4: Extend browser accessibility and smoke expectations**

Scan the registration page with Axe. Keep administrator smoke behavior unchanged and update login headings/links. Do not persist registration passwords in Playwright artifacts.

- [ ] **Step 5: Run complete quality gate**

Run:

```bash
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest -W error -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src scripts
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
docker compose -f compose.yaml config --quiet
docker compose -f example/compose.yaml config --quiet
git diff --check
```

Start a fresh migrated database without bootstrap variables, register the first account through `/auth/register`, and run Playwright with one worker. Expected: all browser tests pass and the first account reaches administrator pages.

- [ ] **Step 6: Commit docs and acceptance coverage**

```bash
git add .env.example README.md docs/operations.md example frontend/e2e tests/unit/test_compose_config.py docs/superpowers/plans/2026-07-28-user-self-service-registration.md
git commit -m "docs: adopt first-registration initialization"
```
