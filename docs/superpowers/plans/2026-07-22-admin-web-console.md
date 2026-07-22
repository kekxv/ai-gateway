# AI Gateway Admin Web Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-ready Chinese administration SPA at `/console/` for operating users, balances, API keys, providers, models, weighted routes, request logs, and TOTP security.

**Architecture:** Keep FastAPI as the API and production web server. A Vue 3 SPA lives in `frontend/`; Vite proxies management API paths to FastAPI during development, while the Docker build compiles the SPA and FastAPI serves the generated files under `/console/` in production. The existing gateway protocol endpoints remain unchanged; the backend gains two read-only endpoints (`GET /auth/me`, `GET /admin/dashboard/summary`) and an additive `total_spent` field on admin user responses.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy asyncio, MySQL 8.4, Vue 3, TypeScript, Vite, Pinia, Vue Router, Element Plus, Axios, Apache ECharts, Vitest, Vue Test Utils, MSW, Playwright, npm, Docker multi-stage builds.

## Global Constraints

- Preserve all existing OpenAI, Claude, and Gemini HTTP/SSE/WebSocket endpoint behavior.
- The console is an administrator-only desktop-first SPA with responsive support down to 768 px.
- All visible copy is Simplified Chinese; do not add an internationalization dependency in this release.
- Mount the production SPA only at `/console/`; keep `/docs`, `/redoc`, `/openapi.json`, `/health`, `/v1/*`, and `/v1beta/*` unchanged.
- Store JWT access and refresh tokens in `sessionStorage`, never `localStorage`; clear both on logout or failed refresh.
- Never persist, log, or redisplay provider credentials, extra headers, passwords, TOTP codes, or full API keys.
- A newly created or rotated API key is shown once in a non-dismissible result dialog with explicit copy/download actions; closing the dialog erases it from component state.
- Decimal money values remain strings in TypeScript and are never converted to JavaScript `number` for API submission.
- Model aliases are catalog/inbound names only. Every route form must label `upstream_model` as the original provider model name and explain that aliases are rewritten before forwarding.
- Configuration lists may use client-side search and pagination for this release; request logs must retain the backend cursor pagination.
- Run backend quality gates with `uv`; run frontend quality gates with npm.
- Use TDD for backend services, frontend stores, API wrappers, and page behavior; commit after every task.

---

## Planned File Structure

```text
frontend/
├── package.json                 # npm scripts and pinned frontend dependencies
├── package-lock.json            # reproducible npm dependency graph
├── tsconfig.json                # strict application TypeScript settings
├── tsconfig.node.json           # Vite/config TypeScript settings
├── eslint.config.ts             # Vue and strict TypeScript lint rules
├── vite.config.ts               # /console base path, FastAPI dev proxy, Vitest config
├── playwright.config.ts         # browser E2E configuration
├── index.html                   # SPA entry document
├── src/
│   ├── main.ts                  # Vue/Pinia/router/Element Plus bootstrap
│   ├── App.vue                  # router outlet only
│   ├── api/
│   │   ├── client.ts            # Axios auth, refresh serialization, normalized errors
│   │   ├── types.ts             # API DTOs preserving decimal strings
│   │   ├── auth.ts              # login, refresh, current-user, TOTP calls
│   │   ├── dashboard.ts         # dashboard summary call
│   │   ├── users.ts             # user, balance, ledger calls
│   │   ├── apiKeys.ts           # API key CRUD and rotation calls
│   │   ├── providers.ts         # provider CRUD and model sync calls
│   │   ├── models.ts            # model, alias, route CRUD calls
│   │   └── requestLogs.ts       # filtered cursor log calls
│   ├── stores/auth.ts           # authenticated session and role enforcement
│   ├── router/index.ts          # lazy routes and guards
│   ├── layouts/AdminLayout.vue  # sidebar, header, account menu, mobile drawer
│   ├── views/
│   │   ├── LoginView.vue
│   │   ├── DashboardView.vue
│   │   ├── ProvidersView.vue
│   │   ├── ModelsView.vue
│   │   ├── UsersView.vue
│   │   ├── ApiKeysView.vue
│   │   ├── RequestLogsView.vue
│   │   ├── SecurityView.vue
│   │   └── NotFoundView.vue
│   ├── components/
│   │   ├── common/PageHeader.vue
│   │   ├── common/StatusTag.vue
│   │   ├── common/JsonViewer.vue
│   │   ├── providers/ProviderFormDrawer.vue
│   │   ├── models/ModelFormDrawer.vue
│   │   ├── models/RouteFormDrawer.vue
│   │   ├── users/UserFormDrawer.vue
│   │   ├── users/BalanceDialog.vue
│   │   ├── users/LedgerDrawer.vue
│   │   ├── api-keys/ApiKeyFormDrawer.vue
│   │   ├── api-keys/SecretResultDialog.vue
│   │   └── request-logs/RequestLogDetailDrawer.vue
│   ├── utils/format.ts
│   ├── styles/index.css
│   └── test/setup.ts
├── tests/                         # Vitest page/component tests
└── e2e/                           # Playwright browser acceptance tests
src/ai_gateway/
├── auth/schemas.py                # current-user response DTO
├── auth/router.py                 # GET /auth/me
├── admin/dashboard.py             # summary queries and response DTOs
├── frontend.py                    # safe `/console/` static serving and SPA fallback
└── main.py                        # dashboard router and console registration
tests/integration/
├── auth/test_me.py
└── admin/test_dashboard.py
tests/unit/test_frontend.py
```

---

### Task 1: Add the current-user session endpoint

**Files:**
- Modify: `src/ai_gateway/auth/schemas.py`
- Modify: `src/ai_gateway/auth/router.py`
- Create: `tests/integration/auth/test_me.py`

**Interfaces:**
- Consumes: existing `current_user` dependency and `User` model.
- Produces: `GET /auth/me -> CurrentUserResponse` with `id`, `email`, `role`, `is_active`, `totp_enabled`, `created_at`, and `updated_at`.

- [ ] **Step 1: Write endpoint contract tests**

```python
async def test_get_me_returns_authenticated_user(auth_client, admin_user, access_token):
    response = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": admin_user.id,
        "email": admin_user.email,
        "role": "admin",
        "is_active": True,
        "totp_enabled": False,
        "created_at": admin_user.created_at.isoformat(),
        "updated_at": admin_user.updated_at.isoformat(),
    }


async def test_get_me_rejects_missing_bearer_token(auth_client):
    response = await auth_client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
```

- [ ] **Step 2: Run the new tests and confirm the endpoint is absent**

Run: `uv run pytest tests/integration/auth/test_me.py -q`

Expected: FAIL because `GET /auth/me` returns `404`.

- [ ] **Step 3: Add the response model and route**

```python
# src/ai_gateway/auth/schemas.py
from datetime import datetime


class CurrentUserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    totp_enabled: bool
    created_at: datetime
    updated_at: datetime
```

```python
# src/ai_gateway/auth/router.py
@router.get("/me", response_model=CurrentUserResponse)
async def get_me(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
```

- [ ] **Step 4: Run focused and existing auth tests**

Run: `uv run pytest tests/integration/auth -q`

Expected: all auth integration tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_gateway/auth/schemas.py src/ai_gateway/auth/router.py tests/integration/auth/test_me.py
git commit -m "feat: expose current admin session"
```

---

### Task 2: Add the dashboard summary API

**Files:**
- Create: `src/ai_gateway/admin/dashboard.py`
- Modify: `src/ai_gateway/main.py`
- Create: `tests/integration/admin/test_dashboard.py`

**Interfaces:**
- Consumes: `User`, `ApiKey`, `Provider`, `Model`, `ModelRoute`, and `RequestLog` tables.
- Produces: `GET /admin/dashboard/summary -> DashboardSummary`; daily buckets are UTC calendar dates and always contain seven entries, including zero-value days.

- [ ] **Step 1: Write summary authorization and aggregation tests**

```python
async def test_dashboard_summary_requires_admin(user_client):
    response = await user_client.get("/admin/dashboard/summary")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_required"


async def test_dashboard_summary_returns_counts_and_seven_utc_days(
    admin_client,
    seeded_dashboard_data,
):
    response = await admin_client.get("/admin/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["users_total"] == 2
    assert payload["active_api_keys"] == 1
    assert payload["providers"] == {"total": 2, "enabled": 1}
    assert payload["models"] == {"total": 2, "enabled": 1}
    assert payload["routes"] == {"total": 3, "enabled": 2, "unavailable": 1}
    assert payload["requests_24h"] == 3
    assert payload["failed_requests_24h"] == 1
    assert payload["cost_24h"] == "0.12500000"
    assert len(payload["daily_usage"]) == 7
    assert payload["daily_usage"][-1]["requests"] == 3
```

- [ ] **Step 2: Run the test and verify the router does not exist**

Run: `uv run pytest tests/integration/admin/test_dashboard.py -q`

Expected: FAIL with `404 Not Found`.

- [ ] **Step 3: Implement typed dashboard responses and aggregate queries**

```python
class ResourceCount(BaseModel):
    total: int
    enabled: int


class RouteCount(ResourceCount):
    unavailable: int


class DailyUsagePoint(BaseModel):
    date: date
    requests: int
    failures: int
    cost: Decimal


class DashboardSummary(BaseModel):
    users_total: int
    active_api_keys: int
    providers: ResourceCount
    models: ResourceCount
    routes: RouteCount
    requests_24h: int
    failed_requests_24h: int
    prompt_tokens_24h: int
    completion_tokens_24h: int
    cost_24h: Decimal
    average_latency_ms_24h: int | None
    daily_usage: list[DailyUsagePoint]
```

Implement `get_dashboard_summary(session, _: AdminUser)` with SQL aggregate expressions using `func.count`, `func.sum`, `func.avg`, and `case`. Use `datetime.now(UTC).replace(tzinfo=None)` for MySQL comparisons, count `RequestStatus.FAILED` as failures, and count `RouteRuntimeState.OPEN` as unavailable. Query raw daily rows from the previous six UTC midnights through now, then fill missing dates in Python with `Decimal("0")`.

- [ ] **Step 4: Register the dashboard router**

```python
from ai_gateway.admin.dashboard import router as dashboard_router

# inside create_app, before gateway protocol routers
app.include_router(dashboard_router)
```

- [ ] **Step 5: Run dashboard and schema tests**

Run: `uv run pytest tests/integration/admin/test_dashboard.py tests/integration/test_schema.py -q`

Expected: PASS, and `/admin/dashboard/summary` appears in OpenAPI.

- [ ] **Step 6: Commit**

```bash
git add src/ai_gateway/admin/dashboard.py src/ai_gateway/main.py tests/integration/admin/test_dashboard.py
git commit -m "feat: add admin dashboard summary"
```

---

### Task 3: Scaffold the Vue application and authenticated API client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/eslint.config.ts`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/stores/auth.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/tests/auth-store.spec.ts`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `/auth/login`, `/auth/refresh`, and `/auth/me`.
- Produces: `apiClient`, `ApiError`, `useAuthStore()`, and strict DTO types used by every page.

- [ ] **Step 1: Initialize npm metadata with exact scripts**

```json
{
  "name": "ai-gateway-console",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc -b && vite build",
    "typecheck": "vue-tsc -b --pretty false",
    "lint": "eslint . --max-warnings=0",
    "test": "vitest run",
    "test:watch": "vitest",
    "e2e": "playwright test"
  }
}
```

Install exact dependency versions and preserve them with npm’s generated lockfile:

```bash
npm install --prefix frontend --save-exact \
  vue@3.5.18 pinia@3.0.3 vue-router@4.5.1 element-plus@2.10.4 \
  @element-plus/icons-vue@2.3.1 axios@1.11.0 echarts@5.6.0 \
  vue-echarts@7.0.3 qrcode.vue@3.6.0
npm install --prefix frontend --save-dev --save-exact \
  vite@7.0.6 @vitejs/plugin-vue@6.0.1 typescript@5.8.3 vue-tsc@3.0.4 \
  vitest@3.2.4 jsdom@26.1.0 @vue/test-utils@2.4.6 msw@2.10.4 \
  eslint@9.31.0 eslint-plugin-vue@10.3.0 typescript-eslint@8.38.0 \
  @types/node@24.1.0 @playwright/test@1.54.1 @axe-core/playwright@4.10.2
```

Commit the generated `package-lock.json`.

Add `/frontend/node_modules/`, `/frontend/dist/`, `/frontend/coverage/`, `/frontend/playwright-report/`, and `/frontend/test-results/` to the repository `.gitignore`.

- [ ] **Step 2: Configure strict TypeScript, Vite, tests, and the development proxy**

```ts
// frontend/vite.config.ts
export default defineConfig({
  base: '/console/',
  plugins: [vue()],
  server: {
    proxy: Object.fromEntries(
      ['/auth', '/admin', '/me', '/health'].map((path) => [
        path,
        { target: process.env.GATEWAY_DEV_URL ?? 'http://127.0.0.1:8000', changeOrigin: true },
      ]),
    ),
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
  },
})
```

Set `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, and `noFallthroughCasesInSwitch` to `true` in `tsconfig.json`. Set the `@` alias to `frontend/src` in both TypeScript and Vite.

Create a flat ESLint configuration using `eslint-plugin-vue`’s essential Vue 3 rules and `typescript-eslint`’s strict type-checked rules. Ignore only `dist/`, `coverage/`, and `playwright-report/`; do not disable `no-explicit-any`, `no-floating-promises`, or Vue accessibility-relevant template checks.

- [ ] **Step 3: Define shared DTOs without converting decimals**

```ts
export type Protocol = 'openai' | 'claude' | 'gemini'
export type UserRole = 'admin' | 'user'
export type RequestStatus = 'started' | 'completed' | 'failed' | 'client_disconnected'
export type RouteRuntimeState = 'closed' | 'open' | 'half_open'
export type ApiKeyScope = 'all' | 'providers' | 'models' | 'providers_and_models'

export interface CurrentUser {
  id: number
  email: string
  role: UserRole
  is_active: boolean
  totp_enabled: boolean
  created_at: string
  updated_at: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
}

export interface ApiErrorBody {
  detail: { code: string; message: string; request_id?: string } | Array<{
    loc: Array<string | number>
    msg: string
    type: string
  }>
}
```

Add the remaining API response and request interfaces using the exact OpenAPI field names already exposed by FastAPI. Define every monetary field (`balance`, `cost`, prices, ledger amounts) as `string`.

- [ ] **Step 4: Write failing auth-store tests**

```ts
it('restores a valid admin session', async () => {
  sessionStorage.setItem('gateway.access_token', 'access')
  sessionStorage.setItem('gateway.refresh_token', 'refresh')
  server.use(http.get('/auth/me', () => HttpResponse.json(adminUser)))

  const store = useAuthStore()
  await store.restore()

  expect(store.user).toEqual(adminUser)
  expect(store.isAdmin).toBe(true)
})

it('clears storage when refresh fails', async () => {
  server.use(
    http.get('/auth/me', () => new HttpResponse(null, { status: 401 })),
    http.post('/auth/refresh', () => new HttpResponse(null, { status: 401 })),
  )
  await expect(useAuthStore().restore()).resolves.toBeUndefined()
  expect(sessionStorage.length).toBe(0)
})
```

- [ ] **Step 5: Implement refresh serialization and error normalization**

```ts
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
  ) {
    super(message)
  }
}

let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  refreshPromise ??= rawClient
    .post<{ access_token: string }>('/auth/refresh', {
      refresh_token: sessionStorage.getItem(REFRESH_TOKEN_KEY),
    })
    .then(({ data }) => {
      sessionStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
      return data.access_token
    })
    .finally(() => { refreshPromise = null })
  return refreshPromise
}
```

The request interceptor injects `Authorization: Bearer <access token>`. The response interceptor retries a request once after a serialized refresh, marks the Axios config with `_retried`, and clears session state if refresh fails. `normalizeApiError` maps FastAPI `{detail:{code,message,request_id}}` and validation arrays into `ApiError` without including submitted secrets.

- [ ] **Step 6: Implement the Pinia store**

The store exposes `user`, `ready`, `authenticated`, `isAdmin`, `login(credentials)`, `restore()`, and `logout()`. `login` stores tokens only after a successful response, calls `/auth/me`, and rejects role `user` with `ApiError(403, "admin_required", "仅管理员可以访问管理控制台")` after clearing tokens.

- [ ] **Step 7: Run frontend unit, lint, and type checks**

Run:

```bash
npm --prefix frontend run test
npm --prefix frontend run lint
npm --prefix frontend run typecheck
```

Expected: all commands exit `0`.

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat: scaffold authenticated vue console"
```

---

### Task 4: Build login, routing, and the administration shell

**Files:**
- Create: `frontend/src/router/index.ts`
- Create: `frontend/src/layouts/AdminLayout.vue`
- Create: `frontend/src/views/LoginView.vue`
- Create: `frontend/src/views/NotFoundView.vue`
- Create: `frontend/src/components/common/PageHeader.vue`
- Create: `frontend/src/components/common/StatusTag.vue`
- Create: `frontend/src/styles/index.css`
- Modify: `frontend/src/main.ts`
- Create: `frontend/tests/login.spec.ts`
- Create: `frontend/tests/router.spec.ts`

**Interfaces:**
- Consumes: `useAuthStore()` and `ApiError.code` values including `totp_required` and `admin_required`.
- Produces: named routes `login`, `dashboard`, `providers`, `models`, `users`, `api-keys`, `request-logs`, `security`, and `not-found`.

- [ ] **Step 1: Write login and navigation guard tests**

```ts
it('asks for a TOTP code only after totp_required', async () => {
  server.use(http.post('/auth/login', () => HttpResponse.json(
    { detail: { code: 'totp_required', message: 'TOTP code is required' } },
    { status: 401 },
  )))
  const wrapper = mount(LoginView, testAppOptions)
  await wrapper.get('[data-test=email]').setValue('admin@example.com')
  await wrapper.get('[data-test=password]').setValue('secret-pass')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.find('[data-test=totp-code]').exists()).toBe(true)
})

it('redirects an unauthenticated console route to login', async () => {
  await router.push('/providers')
  await router.isReady()
  expect(router.currentRoute.value.name).toBe('login')
  expect(router.currentRoute.value.query.redirect).toBe('/providers')
})
```

- [ ] **Step 2: Define lazy routes and an async guard**

```ts
const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    children: [
      { path: '', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
      { path: 'providers', name: 'providers', component: () => import('@/views/ProvidersView.vue') },
      { path: 'models', name: 'models', component: () => import('@/views/ModelsView.vue') },
      { path: 'users', name: 'users', component: () => import('@/views/UsersView.vue') },
      { path: 'api-keys', name: 'api-keys', component: () => import('@/views/ApiKeysView.vue') },
      { path: 'request-logs', name: 'request-logs', component: () => import('@/views/RequestLogsView.vue') },
      { path: 'security', name: 'security', component: () => import('@/views/SecurityView.vue') },
    ],
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue') },
]
```

Create the router with `createWebHistory(import.meta.env.BASE_URL)`. Before protected navigation, call `auth.restore()` once; redirect missing/invalid sessions to `/login?redirect=<fullPath>` and authenticated visits to `/login` back to `/`.

- [ ] **Step 3: Implement the two-stage login form**

The first submission sends `email` and `password`. If the normalized error code is `totp_required`, preserve the email, keep the password in component memory, reveal a six-digit TOTP input, focus it, and resubmit all three values. Clear the password and TOTP value after success or when leaving the page. Disable the submit button during each request.

- [ ] **Step 4: Implement the admin shell**

Use an Element Plus sidebar with the seven protected routes, a header showing the authenticated email, a “安全设置” action, and “退出登录”. Collapse the sidebar below 1200 px and use a drawer below 768 px. Add a skip-to-content link and set the main region to `id="main-content"`.

- [ ] **Step 5: Add global visual tokens**

```css
:root {
  color-scheme: light;
  --gateway-bg: #f4f7fb;
  --gateway-panel: #ffffff;
  --gateway-border: #dfe7f1;
  --gateway-text: #172033;
  --gateway-muted: #667085;
  --gateway-brand: #2563eb;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

body { margin: 0; min-width: 320px; background: var(--gateway-bg); color: var(--gateway-text); }
* { box-sizing: border-box; }
.page-card { background: var(--gateway-panel); border: 1px solid var(--gateway-border); border-radius: 12px; }
```

- [ ] **Step 6: Verify routing and shell tests**

Run: `npm --prefix frontend run test -- login.spec.ts router.spec.ts`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src frontend/tests
git commit -m "feat: add console login and navigation shell"
```

---

### Task 5: Implement the operations dashboard

**Files:**
- Create: `frontend/src/api/dashboard.ts`
- Create: `frontend/src/views/DashboardView.vue`
- Create: `frontend/src/utils/format.ts`
- Create: `frontend/tests/dashboard.spec.ts`

**Interfaces:**
- Consumes: `GET /admin/dashboard/summary` and `DashboardSummary`.
- Produces: overview cards, route-health alert, 24-hour usage metrics, and a seven-day requests/cost chart.

- [ ] **Step 1: Write dashboard rendering tests**

```ts
it('renders summary counts, money, and an unavailable-route warning', async () => {
  server.use(http.get('/admin/dashboard/summary', () => HttpResponse.json(summaryFixture)))
  const wrapper = mount(DashboardView, testAppOptions)
  await flushPromises()
  expect(wrapper.text()).toContain('启用提供商 2 / 3')
  expect(wrapper.text()).toContain('24 小时费用 ¥0.12500000')
  expect(wrapper.text()).toContain('1 条路由处于熔断状态')
})
```

- [ ] **Step 2: Implement formatting helpers**

Export `formatMoney(value: string)`, `formatInteger(value: number)`, `formatDateTime(value: string | null)`, `formatDuration(value: number | null)`, and `formatPercent(numerator, denominator)`. `formatMoney` must retain eight decimal places and must not parse the string through a floating-point number.

- [ ] **Step 3: Build the dashboard page**

Render resource cards for users, active API keys, providers, models, and routes. Render 24-hour request count, failure rate, prompt/completion tokens, exact cost, and average latency. Use one ECharts mixed chart with request/failure bars on the left axis and cost line on the right axis. Dispose the ECharts instance on component unmount and resize it with `ResizeObserver`.

- [ ] **Step 4: Add loading, empty, and failure states**

Use Element Plus skeletons during the first request. Show a retryable result panel on API failure. A seven-day all-zero response is valid and must show an empty-chart annotation rather than an error.

- [ ] **Step 5: Run the dashboard tests and build**

Run:

```bash
npm --prefix frontend run test -- dashboard.spec.ts
npm --prefix frontend run build
```

Expected: PASS and `frontend/dist/index.html` is generated.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/dashboard.ts frontend/src/views/DashboardView.vue frontend/src/utils/format.ts frontend/tests/dashboard.spec.ts
git commit -m "feat: add operations dashboard"
```

---

### Task 6: Implement provider and protocol management

**Files:**
- Create: `frontend/src/api/providers.ts`
- Create: `frontend/src/views/ProvidersView.vue`
- Create: `frontend/src/components/providers/ProviderFormDrawer.vue`
- Create: `frontend/tests/providers.spec.ts`

**Interfaces:**
- Consumes: provider CRUD endpoints and `POST /admin/providers/{id}/sync-models`.
- Produces: searchable provider table and create/edit drawer supporting multiple OpenAI/Claude/Gemini protocol records.

- [ ] **Step 1: Write behavior tests for secret-safe editing and sync**

```ts
it('does not send credential when editing without a replacement', async () => {
  const requests: unknown[] = []
  server.use(http.patch('/admin/providers/1', async ({ request }) => {
    requests.push(await request.json())
    return HttpResponse.json(providerFixture)
  }))
  await openProviderEditorAndSubmit({ name: 'OpenAI Primary', credentialText: '' })
  expect(requests).toEqual([{ name: 'OpenAI Primary' }])
})

it('shows the model sync result', async () => {
  server.use(http.post('/admin/providers/1/sync-models', () => HttpResponse.json({
    provider_id: 1, discovered_models: 12, created_models: 2,
    created_routes: 3, updated_routes: 0, disabled_routes: 1,
  })))
  const wrapper = mount(ProvidersView, testAppOptions)
  await clickSync(wrapper, 1)
  expect(wrapper.text()).toContain('发现 12 个，新增模型 2 个，新增路由 3 条')
})
```

- [ ] **Step 2: Implement the provider API module**

Export `listProviders`, `createProvider`, `updateProvider`, `deleteProvider`, and `syncProviderModels`. Use `PATCH` for edits. The form request builder omits blank replacement credentials and blank replacement `extra_headers`; it never sends `null` for either secret field.

- [ ] **Step 3: Build the provider table**

Columns: name, enabled, protocol badges, auto-load status, last sync time, sync interval, and actions. Client-side search matches provider name, protocol, and base URL. Disable deletion when the backend returns `provider_has_history`; show the backend message and suggest disabling the provider.

- [ ] **Step 4: Build the dynamic protocol form**

The drawer includes provider name, credential JSON editor, enabled, auto-load, interval, and a repeatable protocol section. Every protocol row has protocol enum, HTTP base URL, optional WebSocket URL, optional replacement extra-header JSON, and enabled state. Parse JSON on submit, require a JSON object rather than an array/scalar, and display row-local errors. Preserve protocol `id` when editing.

- [ ] **Step 5: Test and commit**

Run: `npm --prefix frontend run test -- providers.spec.ts && npm --prefix frontend run typecheck`

Expected: PASS.

```bash
git add frontend/src/api/providers.ts frontend/src/views/ProvidersView.vue frontend/src/components/providers frontend/tests/providers.spec.ts
git commit -m "feat: add provider protocol management"
```

---

### Task 7: Implement models, aliases, and weighted routes

**Files:**
- Create: `frontend/src/api/models.ts`
- Create: `frontend/src/views/ModelsView.vue`
- Create: `frontend/src/components/models/ModelFormDrawer.vue`
- Create: `frontend/src/components/models/RouteFormDrawer.vue`
- Create: `frontend/tests/models.spec.ts`
- Create: `frontend/tests/routes.spec.ts`

**Interfaces:**
- Consumes: model CRUD, route CRUD, provider list, and route filters.
- Produces: a master/detail model page where routes are edited in the selected model context.

- [ ] **Step 1: Write alias and upstream-name tests**

```ts
it('submits enabled alias objects and exact decimal price strings', async () => {
  await submitModel({
    canonicalName: 'gpt-4.1',
    aliases: [{ alias: 'fast-chat', enabled: true }],
    inputPrice: '2.00000000',
    outputPrice: '8.00000000',
  })
  expect(lastModelRequest()).toMatchObject({
    canonical_name: 'gpt-4.1',
    aliases: [{ alias: 'fast-chat', enabled: true }],
    input_price_per_million: '2.00000000',
    output_price_per_million: '8.00000000',
  })
})

it('labels the route model as the original provider model name', async () => {
  const wrapper = await openRouteDrawer()
  expect(wrapper.text()).toContain('提供商原始模型名')
  expect(wrapper.text()).toContain('别名在转发前会转换为这里填写的模型名')
})
```

- [ ] **Step 2: Implement model and route API functions**

Export model `list/create/update/delete` calls and route `list/create/update/delete` calls. `listModelRoutes` accepts optional `model_id` and `provider_id`. Keep `source`, `runtime_state`, failure count, disabled-until, and last error fields read-only.

- [ ] **Step 3: Build the model master table and edit drawer**

Columns: display name, canonical name, aliases, input/output price per million tokens, routing strategy, enabled, and route count. Alias rows contain alias text and enabled state; reject duplicate aliases and aliases equal to the canonical name before sending. Use text inputs with decimal regex `^\d{1,12}(\.\d{1,8})?$`.

- [ ] **Step 4: Build the route detail table and drawer**

Selecting a model loads `/admin/model-routes?model_id=<id>`. Columns: provider, protocol, original upstream model, weight, enabled, source, runtime state, failures, disabled until, and last error. Provider selection filters the protocol selector to that provider’s protocols. Weight accepts integers `1..10000`. Display `closed` as healthy, `half_open` as probing, and `open` as unavailable.

- [ ] **Step 5: Enforce destructive-operation semantics**

Confirm all deletes. For `model_has_history` and `model_route_has_history`, keep the record, show a warning, and offer an “改为禁用” action that sends `PATCH {"enabled": false}`. Discovered routes remain editable because the backend supports it, while the `source` badge continues to identify them.

- [ ] **Step 6: Test and commit**

Run: `npm --prefix frontend run test -- models.spec.ts routes.spec.ts && npm --prefix frontend run typecheck`

Expected: PASS.

```bash
git add frontend/src/api/models.ts frontend/src/views/ModelsView.vue frontend/src/components/models frontend/tests/models.spec.ts frontend/tests/routes.spec.ts
git commit -m "feat: manage models aliases and routes"
```

---

### Task 8: Implement users, balances, and ledger history

**Files:**
- Modify: `src/ai_gateway/admin/users.py`
- Modify: `tests/integration/admin/test_users.py`
- Create: `frontend/src/api/users.ts`
- Create: `frontend/src/views/UsersView.vue`
- Create: `frontend/src/components/users/UserFormDrawer.vue`
- Create: `frontend/src/components/users/BalanceDialog.vue`
- Create: `frontend/src/components/users/LedgerDrawer.vue`
- Create: `frontend/tests/users.spec.ts`

**Interfaces:**
- Consumes: user CRUD, balance adjustment, and user ledger endpoints.
- Produces: additive `UserResponse.total_spent`, user management with exact decimal adjustments, and immutable ledger inspection.

- [ ] **Step 1: Add backend coverage for user total spend**

Extend the existing create/list/get user expectations to parse `total_spent` with `Decimal` and compare it to `Decimal("0")`, then seed a usage ledger entry and assert the list response returns its exact accumulated value as a decimal string.

```python
response = await admin_client.get("/admin/users")
user_payload = next(item for item in response.json() if item["id"] == billed_user.id)
assert user_payload["balance"] == "8.75000000"
assert user_payload["total_spent"] == "1.25000000"
```

Run: `uv run pytest tests/integration/admin/test_users.py -q`

Expected: FAIL because `total_spent` is absent.

- [ ] **Step 2: Add `total_spent` to the backend response**

```python
class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    balance: Decimal
    total_spent: Decimal
    created_at: datetime
    updated_at: datetime
```

Set `total_spent=user.account.total_spent` in `_user_response`, then rerun `uv run pytest tests/integration/admin/test_users.py -q` and expect PASS.

- [ ] **Step 3: Write frontend user and balance tests**

```ts
it('omits password when an edit form leaves it blank', async () => {
  await editUser({ id: 2, email: 'member@example.com', password: '' })
  expect(lastUserPatch()).toEqual({ email: 'member@example.com' })
})

it('submits an exact decimal adjustment and unique idempotency key', async () => {
  await adjustBalance({ userId: 2, amount: '10.25000000', reason: '人工充值' })
  expect(lastAdjustment()).toMatchObject({ amount: '10.25000000', reason: '人工充值' })
  expect(lastAdjustment().idempotency_key).toMatch(/^console-/)
})
```

- [ ] **Step 4: Implement user and billing API functions**

Export `listUsers`, `createUser`, `updateUser`, `deleteUser`, `adjustBalance`, and `listLedger`. Generate adjustment idempotency keys as `console-${crypto.randomUUID()}` once when the dialog opens; reuse the same value during retries of that submission.

- [ ] **Step 5: Build the users table and form**

Columns: email, role, active status, balance, total spent, created/updated time, and actions. Create requires password and initial balance; edit makes password optional. Prevent the signed-in administrator from deleting or disabling their own user in the UI, while still treating backend authorization as authoritative.

- [ ] **Step 6: Build adjustment and ledger views**

The balance dialog accepts a signed non-zero decimal amount and reason, previews the resulting direction (“增加” or “扣减”), and shows returned `balance` and `total_spent`. The ledger drawer shows type, amount, balance after, request ID, metadata JSON, and timestamp in descending order.

- [ ] **Step 7: Test and commit**

Run:

```bash
uv run pytest tests/integration/admin/test_users.py -q
npm --prefix frontend run test -- users.spec.ts
npm --prefix frontend run typecheck
```

Expected: PASS.

```bash
git add src/ai_gateway/admin/users.py tests/integration/admin/test_users.py frontend/src/api/users.ts frontend/src/views/UsersView.vue frontend/src/components/users frontend/tests/users.spec.ts
git commit -m "feat: add user billing administration"
```

---

### Task 9: Implement API key scopes and one-time secret handling

**Files:**
- Create: `frontend/src/api/apiKeys.ts`
- Create: `frontend/src/views/ApiKeysView.vue`
- Create: `frontend/src/components/api-keys/ApiKeyFormDrawer.vue`
- Create: `frontend/src/components/api-keys/SecretResultDialog.vue`
- Create: `frontend/tests/api-keys.spec.ts`

**Interfaces:**
- Consumes: API key CRUD/rotation plus user, provider, and model lists.
- Produces: scoped key creation/editing and one-time secret presentation.

- [ ] **Step 1: Write scope and secret-lifetime tests**

```ts
it.each([
  ['all', false, false],
  ['providers', true, false],
  ['models', false, true],
  ['providers_and_models', true, true],
])('shows selectors required by scope %s', async (scope, providersVisible, modelsVisible) => {
  const wrapper = await openApiKeyForm(scope)
  expect(wrapper.find('[data-test=provider-ids]').exists()).toBe(providersVisible)
  expect(wrapper.find('[data-test=model-ids]').exists()).toBe(modelsVisible)
})

it('erases a one-time key when the result dialog closes', async () => {
  const wrapper = await createApiKeyReturning('sk-gw-once-only')
  expect(wrapper.text()).toContain('sk-gw-once-only')
  await wrapper.get('[data-test=secret-confirm-close]').trigger('click')
  expect(wrapper.text()).not.toContain('sk-gw-once-only')
})
```

- [ ] **Step 2: Implement API key operations**

Export `listApiKeys(userId?)`, `createApiKey`, `updateApiKey`, `deleteApiKey`, and `rotateApiKey`. Represent expiry as an ISO timestamp or `null`. The UI must never place `ApiKeyCreatedResponse.key` in Pinia, router state, query parameters, session storage, console output, or notifications.

- [ ] **Step 3: Build the key table and scoped form**

Columns: name, owner email, key prefix, scope, enabled, expiry, last used, and created time. Scope behavior:

- `all`: submit empty `provider_ids` and `model_ids`.
- `providers`: require at least one provider and submit empty `model_ids`.
- `models`: require at least one model and submit empty `provider_ids`.
- `providers_and_models`: require at least one provider and one model.

- [ ] **Step 4: Build the one-time result dialog**

Make the dialog non-dismissible by backdrop or escape key. Provide “复制”, “下载 .txt”, and an acknowledgement checkbox reading “我已安全保存，此密钥关闭后无法再次查看”. Enable close only after acknowledgement. Revoke the object URL immediately after download.

- [ ] **Step 5: Implement rotation semantics**

Require confirmation that rotation disables the old key. After success, replace the list entry with the new key metadata and open the same one-time result dialog. When the backend returns `api_key_inactive`, refresh the table and explain that only an active key can be rotated.

- [ ] **Step 6: Test and commit**

Run: `npm --prefix frontend run test -- api-keys.spec.ts && npm --prefix frontend run typecheck`

Expected: PASS.

```bash
git add frontend/src/api/apiKeys.ts frontend/src/views/ApiKeysView.vue frontend/src/components/api-keys frontend/tests/api-keys.spec.ts
git commit -m "feat: add scoped api key management"
```

---

### Task 10: Implement request-log search and detail inspection

**Files:**
- Create: `frontend/src/api/requestLogs.ts`
- Create: `frontend/src/views/RequestLogsView.vue`
- Create: `frontend/src/components/common/JsonViewer.vue`
- Create: `frontend/src/components/request-logs/RequestLogDetailDrawer.vue`
- Create: `frontend/tests/request-logs.spec.ts`

**Interfaces:**
- Consumes: filtered `GET /admin/request-logs` cursor pages and `GET /admin/request-logs/{id}`.
- Produces: filterable log table, cursor navigation, and redacted request/response detail display.

- [ ] **Step 1: Write filter and cursor tests**

```ts
it('sends supported filters and resets the cursor stack', async () => {
  const requests: URL[] = []
  server.use(http.get('/admin/request-logs', ({ request }) => {
    requests.push(new URL(request.url))
    return HttpResponse.json({ items: [], next_cursor: null })
  }))
  const wrapper = mount(RequestLogsView, testAppOptions)
  await setLogFilters(wrapper, { status: 'failed', protocol: 'claude', userId: '2' })
  expect(requests.at(-1)?.searchParams.get('status')).toBe('failed')
  expect(requests.at(-1)?.searchParams.get('protocol')).toBe('claude')
  expect(requests.at(-1)?.searchParams.get('user_id')).toBe('2')
  expect(wrapper.vm.cursorStack).toEqual([])
})
```

- [ ] **Step 2: Implement typed log query serialization**

Support `request_id`, `user_id`, `api_key_id`, `model_id`, `provider_id`, `status`, `protocol`, `created_from`, `created_to`, `cursor`, and `page_size`. Omit empty values. Convert local date-range values to ISO timestamps before submission.

- [ ] **Step 3: Build cursor-based navigation**

Keep an in-memory stack of page-start cursors. “下一页” pushes the current start cursor and requests `next_cursor`; “上一页” pops and requests the previous start cursor. Any filter or page-size change resets the stack and starts from no cursor. Do not infer total pages because the API intentionally does not return a total.

- [ ] **Step 4: Build the table and detail drawer**

Columns: request ID, user/key, model/provider/route, inbound→outbound protocol, transport/stream, status/HTTP code, tokens, exact cost, latency/first token, error code, and created time. The detail drawer loads only when opened and renders metadata plus request/response JSON using `<pre>` with escaped text, line wrapping, copy buttons, and collapsed sections. Never use `v-html`.

- [ ] **Step 5: Test and commit**

Run: `npm --prefix frontend run test -- request-logs.spec.ts && npm --prefix frontend run typecheck`

Expected: PASS.

```bash
git add frontend/src/api/requestLogs.ts frontend/src/views/RequestLogsView.vue frontend/src/components/common/JsonViewer.vue frontend/src/components/request-logs frontend/tests/request-logs.spec.ts
git commit -m "feat: add request log explorer"
```

---

### Task 11: Implement TOTP security settings

**Files:**
- Modify: `frontend/src/api/auth.ts`
- Create: `frontend/src/views/SecurityView.vue`
- Create: `frontend/tests/security.spec.ts`

**Interfaces:**
- Consumes: `POST /auth/totp/setup`, `POST /auth/totp/confirm`, and current `totp_enabled` state.
- Produces: QR-based enrollment and re-enrollment with current-code verification.

- [ ] **Step 1: Write enrollment state tests**

```ts
it('renders the QR only after setup succeeds and confirms six digits', async () => {
  server.use(
    http.post('/auth/totp/setup', () => HttpResponse.json({ otpauth_uri: 'otpauth://totp/example' })),
    http.post('/auth/totp/confirm', () => HttpResponse.json({ totp_enabled: true })),
  )
  const wrapper = mount(SecurityView, testAppOptions)
  await wrapper.get('[data-test=start-totp]').trigger('click')
  expect(wrapper.findComponent(QrcodeVue).props('value')).toBe('otpauth://totp/example')
  await wrapper.get('[data-test=confirm-code]').setValue('123456')
  await wrapper.get('[data-test=confirm-totp]').trigger('click')
  expect(useAuthStore().user?.totp_enabled).toBe(true)
})
```

- [ ] **Step 2: Implement new-enrollment and replacement flows**

If TOTP is disabled, setup sends `{}`. If enabled, require the current six-digit code and send `{current_totp_code: code}`. Render the returned URI as a QR code and offer a copyable manual URI. Confirm with a separate six-digit code. Erase URI and both codes after confirm, cancellation, logout, or unmount.

- [ ] **Step 3: Handle auth-specific errors**

Map `current_totp_required`, `invalid_totp`, and `totp_not_configured` to field-level Chinese messages. After confirmation, call `/auth/me` to refresh the store instead of mutating only local page state.

- [ ] **Step 4: Test and commit**

Run: `npm --prefix frontend run test -- security.spec.ts && npm --prefix frontend run typecheck`

Expected: PASS.

```bash
git add frontend/src/api/auth.ts frontend/src/views/SecurityView.vue frontend/tests/security.spec.ts
git commit -m "feat: add totp security settings"
```

---

### Task 12: Serve the SPA from FastAPI and build it into Docker

**Files:**
- Create: `src/ai_gateway/frontend.py`
- Modify: `src/ai_gateway/main.py`
- Modify: `Dockerfile`
- Modify: `.dockerignore`
- Create: `tests/unit/test_frontend.py`

**Interfaces:**
- Consumes: Vite output at `<repository>/frontend/dist`.
- Produces: `/console`, `/console/`, `/console/assets/*`, and SPA history fallbacks under `/console/*`; absent local builds leave the backend usable and do not register console routes.

- [ ] **Step 1: Write isolated static-serving tests**

```python
def test_console_serves_index_and_history_fallback(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>console</html>")
    (dist / "assets" / "app.js").write_text("export {}")
    app = FastAPI()
    mount_console(app, dist)

    with TestClient(app) as client:
        assert client.get("/console/").text == "<html>console</html>"
        assert client.get("/console/providers").text == "<html>console</html>"
        assert client.get("/console/assets/app.js").status_code == 200


def test_console_is_not_registered_when_dist_is_missing(tmp_path):
    app = FastAPI()
    mount_console(app, tmp_path / "missing")
    with TestClient(app) as client:
        assert client.get("/console/").status_code == 404
```

- [ ] **Step 2: Implement restricted SPA serving**

```python
def mount_console(app: FastAPI, dist_dir: Path) -> None:
    index = dist_dir / "index.html"
    assets = dist_dir / "assets"
    if not index.is_file():
        return
    if assets.is_dir():
        app.mount("/console/assets", StaticFiles(directory=assets), name="console-assets")

    async def console_index() -> FileResponse:
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    app.add_api_route("/console", console_index, include_in_schema=False)
    app.add_api_route("/console/", console_index, include_in_schema=False)
    app.add_api_route("/console/{path:path}", console_index, include_in_schema=False)
```

Register this only after all API and gateway routers. Resolve the default dist directory as `Path(__file__).resolve().parents[2] / "frontend" / "dist"`. `index.html` must remain `no-cache` so deployments do not strand browsers on an obsolete asset manifest.

- [ ] **Step 3: Add a frontend Docker build stage**

```dockerfile
FROM node:22-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build
```

Copy `/frontend/dist` from that stage to `/app/frontend/dist` in the existing Python runtime image. Keep the runtime non-root, read-only, capability-free, and free of Node/npm.

- [ ] **Step 4: Verify unit tests and the container artifact**

Run:

```bash
uv run pytest tests/unit/test_frontend.py -q
npm --prefix frontend run build
docker build -t lean-ai-gateway:console-test .
docker run --rm --entrypoint python lean-ai-gateway:console-test -c "from pathlib import Path; assert Path('/app/frontend/dist/index.html').is_file()"
```

Expected: all commands exit `0`.

- [ ] **Step 5: Commit**

```bash
git add src/ai_gateway/frontend.py src/ai_gateway/main.py Dockerfile .dockerignore tests/unit/test_frontend.py
git commit -m "feat: serve console in production image"
```

---

### Task 13: Add browser acceptance tests, CI gates, and operations documentation

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/admin-console.spec.ts`
- Modify: `.github/workflows/ci.yml` if present, otherwise create it using the existing backend CI commands
- Modify: `README.md`
- Modify: `docs/operations.md`

**Interfaces:**
- Consumes: migrated MySQL test database, a running FastAPI app with built frontend, and seeded administrator credentials.
- Produces: repeatable browser smoke coverage and documented local/production workflows.

- [ ] **Step 1: Configure Playwright against the built application**

```ts
export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: process.env.CONSOLE_BASE_URL ?? 'http://127.0.0.1:8000/console/',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: process.env.CONSOLE_BASE_URL ? undefined : {
    command: 'uv run uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8000',
    cwd: '..',
    url: 'http://127.0.0.1:8000/health',
    reuseExistingServer: !process.env.CI,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
```

- [ ] **Step 2: Add a complete administrator smoke journey**

The browser test reads `E2E_ADMIN_EMAIL` and `E2E_ADMIN_PASSWORD`, logs in, verifies dashboard metrics, creates a disabled test provider, creates a model with an alias containing `e2e-friendly-model`, creates a weighted route with `upstream_model="e2e-original-model"`, creates a user and balance adjustment, creates a model-scoped API key and acknowledges its one-time secret, filters request logs, then disables or removes records in reverse dependency order. Use unique names containing `crypto.randomUUID()` so retries do not collide.

- [ ] **Step 3: Add accessibility assertions**

Run Axe on login, dashboard, providers, models, users, API keys, logs, and security pages. Fail for `critical` and `serious` violations. Also verify keyboard focus reaches the skip link, navigation, page heading, and first primary action in that order.

- [ ] **Step 4: Extend CI**

Add a Node 22 job or steps that run:

```bash
npm ci --prefix frontend
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
export GATEWAY_BOOTSTRAP_PASSWORD='console-e2e-password'
uv run python scripts/create_admin.py \
  --email console-e2e@example.com \
  --password-env GATEWAY_BOOTSTRAP_PASSWORD
export E2E_ADMIN_EMAIL='console-e2e@example.com'
export E2E_ADMIN_PASSWORD="$GATEWAY_BOOTSTRAP_PASSWORD"
npm exec --prefix frontend -- playwright install --with-deps chromium
npm --prefix frontend run e2e
unset GATEWAY_BOOTSTRAP_PASSWORD E2E_ADMIN_EMAIL E2E_ADMIN_PASSWORD
```

Preserve the existing Python 3.12, MySQL 8.4, Ruff, formatting, mypy, pytest coverage, Docker build, and Compose validation gates.

- [ ] **Step 5: Document development and production usage**

Add these workflows:

```bash
# terminal 1: backend
uv run uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8000 --reload

# terminal 2: frontend dev server
npm ci --prefix frontend
npm --prefix frontend run dev
# open http://127.0.0.1:5173/console/

# production-style local build
npm --prefix frontend run build
uv run uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000/console/
```

Document that the public gateway remains on port 8000, the console uses the same origin, and reverse proxies must forward `/console/`, `/auth/`, `/admin/`, and `/me/` while retaining `/v1/` and `/v1beta/` for client traffic.

- [ ] **Step 6: Run all release gates**

Run:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
GATEWAY_TEST_DATABASE_URL='mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway_test' uv run pytest -W error --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run e2e
docker build -t lean-ai-gateway:console-final .
docker compose config --quiet
```

Expected: every command exits `0`, backend coverage remains at least 90%, and Playwright passes in Chromium.

- [ ] **Step 7: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e .github/workflows/ci.yml README.md docs/operations.md
git commit -m "test: cover and document admin console"
```

---

## Final Acceptance Checklist

- [ ] An administrator can log in with password-only or password-plus-TOTP authentication.
- [ ] A non-admin account cannot enter the console.
- [ ] Token refresh is serialized and a failed refresh clears the browser session.
- [ ] Dashboard totals and seven-day usage are produced by backend aggregates, not by summing truncated UI lists.
- [ ] Providers support multiple protocols, replacement-only secret fields, model synchronization, and enable/disable operations.
- [ ] Models support aliases, exact prices, weighted routes, route health visibility, and original upstream model names.
- [ ] Users support role/status management, exact balance adjustments, total spend visibility, and ledger history.
- [ ] API keys support all four scope modes and never retain the one-time raw key after acknowledgement.
- [ ] Request logs support every backend filter, cursor navigation, and safe request/response JSON inspection.
- [ ] TOTP setup and replacement erase URI/code data when the flow ends.
- [ ] `/console/*` history routes work after browser refresh without intercepting API or model gateway paths.
- [ ] The production Python image contains compiled assets but no Node runtime.
- [ ] Backend, frontend, browser, Docker, and Compose quality gates all pass.
