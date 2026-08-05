# Billing Statistics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a role-aware billing-statistics page for administrators and regular users, with selectable time ranges, multi-dimension filters, KPIs, charts, and textual breakdowns.

**Architecture:** Keep the dashboard summary unchanged. A shared aggregation service powers `/admin/billing-statistics` and `/user/billing-statistics`: the administrator endpoint exposes provider/model/API-key dimensions plus internal cost and gross profit, while the user endpoint always scopes rows to the authenticated user and exposes only model/API-key dimensions and that user's billed amount. One Vue page chooses the endpoint and visible controls from `auth.isAdmin`, preserves Decimal amounts, zero-fills daily points, and renders the role-appropriate result with ECharts.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, Alembic, MySQL, pytest, Vue 3, TypeScript, Element Plus, ECharts, vue-echarts, Vitest, MSW.

## Global Constraints

- The `/billing-statistics` page is visible to administrators and regular users; it must not use `requiresAdmin` route metadata.
- `/user/billing-statistics` always adds `RequestLog.user_id == current_user.id`; it never accepts a user ID or provider ID from the client.
- Regular users never receive provider identities, upstream cost (`cost_amount`), or gross profit; administrators retain those fields and the provider dimension.
- API timestamps must include a timezone, are normalized to UTC, include both range endpoints, and cannot span more than 366 days.
- The date picker displays browser-local time with the current timezone label; the client sends `toISOString()` values and daily buckets are UTC calendar dates.
- The initial range is the preceding seven 24-hour periods ending at current browser time.
- Empty multi-selects mean no filter; selected provider/model/API-key dimensions are intersected rather than unioned.
- Administrators get provider, model, and API-key selectors; regular users get model and their own API-key selectors. Every selector uses `ElSelect` with `multiple`, `filterable`, and `collapse-tags`.
- API-key labels never include an email address. Administrator labels are `名称 · #ID`; regular-user labels are only the key name.
- Monetary values remain decimal strings until rendered by existing format helpers.
- A missing historical relation is represented as `未关联供应商`, `未关联模型`, or `未关联 API Key`, keeping breakdowns reconcilable with totals.
- Request count includes every request-log row in the range; failed count includes only status `failed`, matching the existing dashboard. Costs are summed from persisted values even when a failed or disconnected request has non-zero usage.
- Dimension queries are ordered in SQL by `SUM(RequestLog.cost) DESC`; the frontend does not sort decimal strings. Charts show the first 20 rows and paginated tables retain the complete breakdown.
- `echarts` and `vue-echarts` are already installed; no visualization dependency is added.

---

### Task 1: Index request logs for analytics ranges

**Files:**
- Modify: `src/ai_gateway/db/models/audit.py:26-33`
- Create: `migrations/versions/0017_billing_statistics_indexes.py`
- Modify: `src/ai_gateway/main.py:66`
- Create: `tests/integration/migrations/test_0017_billing_statistics_indexes.py`

**Interfaces:**
- Produces indexes `ix_request_logs_created_at` and `ix_request_logs_model_created_at`; existing provider/API-key indexes remain unchanged.

- [ ] **Step 1: Write the failing migration test**

```python
def _run_0017(connection: Connection, operation: str) -> None:
    path = Path("migrations/versions/0017_billing_statistics_indexes.py")
    spec = spec_from_file_location("migration_0017", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load migration 0017")
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = Operations(MigrationContext.configure(connection))
    getattr(migration, operation)()

def _upgrade_from_0017(connection: Connection) -> None:
    _run_0017(connection, "upgrade")

def _downgrade_from_0017(connection: Connection) -> None:
    _run_0017(connection, "downgrade")

async def test_migration_0017_creates_billing_statistics_indexes(test_engine: AsyncEngine) -> None:
    async with test_engine.begin() as connection:
        await connection.run_sync(_downgrade_from_0017)
        await connection.run_sync(_upgrade_from_0017)
        indexes = await connection.run_sync(
            lambda sync_connection: {
                index["name"]: index["column_names"]
                for index in inspect(sync_connection).get_indexes("request_logs")
            }
        )
    assert indexes["ix_request_logs_created_at"] == ["created_at"]
    assert indexes["ix_request_logs_model_created_at"] == ["model_id", "created_at"]

async def test_migration_0017_downgrade_removes_only_new_indexes(test_engine: AsyncEngine) -> None:
    async with test_engine.begin() as connection:
        await connection.run_sync(_downgrade_from_0017)
        indexes = await connection.run_sync(
            lambda sync_connection: {
                index["name"] for index in inspect(sync_connection).get_indexes("request_logs")
            }
        )
        await connection.run_sync(_upgrade_from_0017)
    assert "ix_request_logs_created_at" not in indexes
    assert "ix_request_logs_model_created_at" not in indexes
    assert "ix_request_logs_api_key_created_at" in indexes
    assert "ix_request_logs_provider_created_at" in indexes
```

- [ ] **Step 2: Run the red test**

Run: `uv run pytest tests/integration/migrations/test_0017_billing_statistics_indexes.py -q`

Expected: FAIL because revision 0017 does not exist.

- [ ] **Step 3: Add metadata and migration**

```python
# RequestLog.__table_args__
Index("ix_request_logs_created_at", "created_at"),
Index("ix_request_logs_model_created_at", "model_id", "created_at"),

# migrations/versions/0017_billing_statistics_indexes.py
revision = "0017"
down_revision = "0016"

def upgrade() -> None:
    op.create_index("ix_request_logs_created_at", "request_logs", ["created_at"])
    op.create_index("ix_request_logs_model_created_at", "request_logs", ["model_id", "created_at"])

def downgrade() -> None:
    op.drop_index("ix_request_logs_model_created_at", table_name="request_logs")
    op.drop_index("ix_request_logs_created_at", table_name="request_logs")
```

Set `REQUIRED_MIGRATION_HEAD = "0017"`.

- [ ] **Step 4: Run the green test**

Run: `uv run pytest tests/integration/migrations/test_0017_billing_statistics_indexes.py -q`

Expected: PASS, proving the migration's own upgrade and downgrade operations rather than only the final ORM metadata.

- [ ] **Step 5: Commit**

```bash
git add src/ai_gateway/db/models/audit.py migrations/versions/0017_billing_statistics_indexes.py src/ai_gateway/main.py tests/integration/migrations/test_0017_billing_statistics_indexes.py
git commit -m "perf: index request logs for billing statistics"
```

### Task 2: Add role-scoped aggregate endpoints

**Files:**
- Create: `src/ai_gateway/admin/billing_statistics.py`
- Modify: `src/ai_gateway/main.py:18-25,281-282`
- Create: `tests/integration/admin/test_billing_statistics.py`

**Interfaces:**
- Consumes for administrators: `GET /admin/billing-statistics?start_at=2026-07-20T00:00:00Z&end_at=2026-07-22T23:59:59Z&provider_ids=1&provider_ids=2&model_ids=3&api_key_ids=4`.
- Consumes for regular users: `GET /user/billing-statistics?start_at=2026-07-20T00:00:00Z&end_at=2026-07-22T23:59:59Z&model_ids=3&api_key_ids=4`.
- Produces `AdminBillingStatisticsResponse` with provider/model/API-key breakdowns and internal financials, or `UserBillingStatisticsResponse` with model/API-key breakdowns and no provider/internal-cost fields.

- [ ] **Step 1: Write failing endpoint tests**

```python
response = await admin_client.get(
    "/admin/billing-statistics",
    params=[
        ("start_at", "2026-07-20T00:00:00Z"),
        ("end_at", "2026-07-22T23:59:59Z"),
        ("provider_ids", "1"),
        ("provider_ids", "2"),
        ("model_ids", "3"),
        ("api_key_ids", "4"),
    ],
)
assert response.status_code == 200
assert response.json()["totals"]["user_cost"] == "0.30000000"
assert response.json()["totals"]["cost_amount"] == "0.18000000"
assert response.json()["totals"]["gross_profit"] == "0.12000000"
assert [point["date"] for point in response.json()["daily_usage"]] == [
    "2026-07-20", "2026-07-21", "2026-07-22"
]
assert (await user_client.get("/admin/billing-statistics", params={
    "start_at": "2026-07-20T00:00:00Z", "end_at": "2026-07-20T23:59:59Z",
})).status_code == 403

own_response = await user_client.get(
    "/user/billing-statistics",
    params=[
        ("start_at", "2026-07-20T00:00:00Z"),
        ("end_at", "2026-07-22T23:59:59Z"),
        ("model_ids", "3"),
        ("api_key_ids", "4"),
    ],
)
assert own_response.status_code == 200
assert own_response.json()["totals"]["user_cost"] == "0.20000000"
assert "cost_amount" not in own_response.json()["totals"]
assert "gross_profit" not in own_response.json()["totals"]
assert "provider_stats" not in own_response.json()
assert {row["id"] for row in own_response.json()["api_key_stats"]} == {4}
```

Seed two users with distinct provider/model/API-key combinations, `NULL` relations, a blank middle day, and records one second outside both bounds. Prove the user endpoint cannot include the second user's rows even if the same model ID is selected. Assert missing-timezone, reversed, and greater-than-366-day ranges get HTTP 422; assert empty ranges return zero totals, zero-filled dates, and empty breakdowns; assert OpenAPI documents all repeated list parameters.

- [ ] **Step 2: Run the red test**

Run: `uv run pytest tests/integration/admin/test_billing_statistics.py -q`

Expected: FAIL with `404 Not Found`.

- [ ] **Step 3: Implement typed schemas and shared predicates**

```python
class UserBillingTotals(BaseModel):
    requests: int
    failed_requests: int
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    user_cost: Decimal
    average_latency_ms: int | None

class AdminBillingTotals(UserBillingTotals):
    cost_amount: Decimal
    gross_profit: Decimal

class UserBillingDailyPoint(UserBillingTotals):
    date: date

class AdminBillingDailyPoint(AdminBillingTotals):
    date: date

class UserBillingDimensionStat(UserBillingTotals):
    id: int | None
    name: str

class AdminBillingDimensionStat(AdminBillingTotals):
    id: int | None
    name: str

class UserBillingStatisticsResponse(BaseModel):
    totals: UserBillingTotals
    daily_usage: list[UserBillingDailyPoint]
    model_stats: list[UserBillingDimensionStat]
    api_key_stats: list[UserBillingDimensionStat]

class AdminBillingStatisticsResponse(BaseModel):
    totals: AdminBillingTotals
    daily_usage: list[AdminBillingDailyPoint]
    provider_stats: list[AdminBillingDimensionStat]
    model_stats: list[AdminBillingDimensionStat]
    api_key_stats: list[AdminBillingDimensionStat]

def apply_billing_filters(query: Select[Any], *, start_at: datetime, end_at: datetime,
                          owner_user_id: int | None, provider_ids: list[int],
                          model_ids: list[int], api_key_ids: list[int]) -> Select[Any]:
    query = query.where(RequestLog.created_at >= start_at, RequestLog.created_at <= end_at)
    if owner_user_id is not None:
        query = query.where(RequestLog.user_id == owner_user_id)
    if provider_ids:
        query = query.where(RequestLog.provider_id.in_(provider_ids))
    if model_ids:
        query = query.where(RequestLog.model_id.in_(model_ids))
    if api_key_ids:
        query = query.where(RequestLog.api_key_id.in_(api_key_ids))
    return query
```

Define repeated filters with `Annotated[list[int], Query()]`, deduplicate them, and reject more than 200 selected IDs per dimension. Reject a timestamp whose `utcoffset()` is `None`, then normalize with `value.astimezone(UTC).replace(tzinfo=None)`. Use the predicate for totals, daily, and each outer-joined dimension query; pass `owner_user_id=None` from the administrator route and the authenticated user's ID from the user route. Coalesce token and decimal sums to zero, derive administrator gross profit as user cost minus cost amount, zero-fill every UTC date, label absent dimensions, and order dimension queries in SQL by `SUM(RequestLog.cost) DESC`. Register both routers in `create_app()`.

- [ ] **Step 4: Run the green test**

Run: `uv run pytest tests/integration/admin/test_billing_statistics.py -q`

Expected: PASS for role isolation, response-field privacy, repeated parameters, decimals, timezone/range boundaries, AND semantics, empty data, zero-fill, and authorization.

- [ ] **Step 5: Commit**

```bash
git add src/ai_gateway/admin/billing_statistics.py src/ai_gateway/main.py tests/integration/admin/test_billing_statistics.py
git commit -m "feat: add filtered billing statistics API"
```

### Task 3: Add role-aware client contracts and shared navigation

**Files:**
- Create: `frontend/src/api/billingStatistics.ts`
- Modify: `frontend/src/api/types.ts:106-164`
- Modify: `frontend/src/router/index.ts:28-75`
- Modify: `frontend/src/layouts/AdminLayout.vue:20-58`
- Modify: `frontend/tests/router.spec.ts`
- Modify: `frontend/tests/admin-layout.spec.ts`

**Interfaces:**
- Produces typed `getAdminBillingStatistics` and `getUserBillingStatistics`, a lazy `/billing-statistics` route, and a `账单统计` sidebar item visible to both roles.

- [ ] **Step 1: Write failing route/navigation tests**

```ts
const statisticsRoute = shellRoute?.children?.find((route) => route.name === 'billing-statistics')
expect(statisticsRoute?.meta?.requiresAdmin).not.toBe(true)
expect(typeof statisticsRoute?.component).toBe('function')
expect(adminWrapper.text()).toContain('账单统计')
expect(userWrapper.text()).toContain('账单统计')

await regularUserRouter.push('/billing-statistics')
expect(regularUserRouter.currentRoute.value.name).toBe('billing-statistics')
```

- [ ] **Step 2: Run the red tests**

Run: `npm --prefix frontend run test -- tests/router.spec.ts tests/admin-layout.spec.ts`

Expected: FAIL because the route and menu item are absent.

- [ ] **Step 3: Serialize each selected ID as a repeated parameter**

```ts
export interface UserBillingStatisticsQuery {
  startAt: string
  endAt: string
  modelIds: number[]
  apiKeyIds: number[]
}

export interface AdminBillingStatisticsQuery extends UserBillingStatisticsQuery {
  providerIds: number[]
}

function commonParams(query: UserBillingStatisticsQuery): URLSearchParams {
  const params = new URLSearchParams({ start_at: query.startAt, end_at: query.endAt })
  query.modelIds.forEach((id) => params.append('model_ids', String(id)))
  query.apiKeyIds.forEach((id) => params.append('api_key_ids', String(id)))
  return params
}

export async function getAdminBillingStatistics(query: AdminBillingStatisticsQuery, signal?: AbortSignal): Promise<AdminBillingStatisticsResponse> {
  const params = commonParams(query)
  query.providerIds.forEach((id) => params.append('provider_ids', String(id)))
  const { data } = await apiClient.get<AdminBillingStatisticsResponse>('/admin/billing-statistics', { params, signal })
  return data
}

export async function getUserBillingStatistics(query: UserBillingStatisticsQuery, signal?: AbortSignal): Promise<UserBillingStatisticsResponse> {
  const { data } = await apiClient.get<UserBillingStatisticsResponse>('/user/billing-statistics', { params: commonParams(query), signal })
  return data
}
```

Add TypeScript counterparts for `UserBillingTotals`, `AdminBillingTotals`, both daily/dimension row types, and both response types; all money fields remain strings. Add route metadata `{ title: '账单统计', userTitle: '账单统计' }` without `requiresAdmin`, and add a navigation item without `requiresAdmin`.

- [ ] **Step 4: Run the green tests**

Run: `npm --prefix frontend run test -- tests/router.spec.ts tests/admin-layout.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/billingStatistics.ts frontend/src/api/types.ts frontend/src/router/index.ts frontend/src/layouts/AdminLayout.vue frontend/tests/router.spec.ts frontend/tests/admin-layout.spec.ts
git commit -m "feat: add billing statistics navigation"
```

### Task 4: Build filtering, KPIs, and charts

**Files:**
- Create: `frontend/src/views/BillingStatisticsView.vue`
- Create: `frontend/tests/billing-statistics.spec.ts`
- Create: `frontend/e2e/billing-statistics.spec.ts`

**Interfaces:**
- Administrators consume `getAdminBillingStatistics`, `listProviders`, `listModels`, and `listApiKeys`.
- Regular users consume `getUserBillingStatistics`, `listAvailableModels`, and `listOwnApiKeys`.
- Produces shared date/model/API-key controls; administrator-only provider, upstream-cost, gross-profit, and provider-breakdown regions; and role-appropriate charts/tables.

- [ ] **Step 1: Write failing page behavior tests**

```ts
expect(adminWrapper.getComponent('[data-test="billing-provider-filter"]').props('multiple')).toBe(true)
expect(adminWrapper.get('[data-test="billing-api-key-option-4"]').text()).toBe('生产密钥 · #4')
expect(adminWrapper.get('[data-test="billing-api-key-option-7"]').text()).toBe('生产密钥 · #7')
expect(adminWrapper.text()).not.toContain('owner@example.com')
await adminWrapper.get('[data-test="billing-apply"]').trigger('click')
expect(adminRequest.searchParams.getAll('provider_ids')).toEqual(['1', '2'])
expect(adminRequest.searchParams.getAll('model_ids')).toEqual(['3'])
expect(adminRequest.searchParams.getAll('api_key_ids')).toEqual(['4'])
expect(adminWrapper.findAll('.v-chart-stub')).toHaveLength(4)

expect(userWrapper.find('[data-test="billing-provider-filter"]').exists()).toBe(false)
expect(userWrapper.get('[data-test="billing-api-key-option-4"]').text()).toBe('生产密钥')
expect(userWrapper.text()).not.toContain('成本')
expect(userWrapper.text()).not.toContain('毛利')
expect(userWrapper.text()).not.toContain('供应商分布')
expect(userWrapper.findAll('.v-chart-stub')).toHaveLength(3)
expect(userRequest.pathname).toBe('/user/billing-statistics')
```

Use MSW responses for both aggregate endpoints and both role-specific catalog sets. Give administrator keys 4 and 7 the same name and different IDs to prove the label disambiguation. The administrator fixture includes provider/internal-cost fields; the user fixture intentionally omits them. Both include a failed request, a zero-valued middle daily point, literal money strings, and an unlinked permitted-dimension row. Stub `vue-echarts` as `dashboard.spec.ts` does, then assert administrator and user trend series differ exactly by the protected financial fields. Add tests that reset restores the seven-day range, retry retains filters, stale responses cannot replace a newer query, a catalog failure does not block an unfiltered aggregate request, and an invalid range is rejected before an HTTP call.

- [ ] **Step 2: Run the red page test**

Run: `npm --prefix frontend run test -- tests/billing-statistics.spec.ts`

Expected: FAIL because the view is absent.

- [ ] **Step 3: Implement controls and view state**

```vue
<ElDatePicker v-model="selectedRange" type="datetimerange" range-separator="至" :clearable="false" data-test="billing-date-range" />
<span class="timezone-note">当前时区：{{ browserTimeZone }}</span>
<ElSelect v-if="auth.isAdmin" v-model="selectedProviderIds" multiple filterable collapse-tags data-test="billing-provider-filter">
  <ElOption v-for="provider in providers" :key="provider.id" :label="provider.name" :value="provider.id" />
</ElSelect>
<ElSelect v-model="selectedModelIds" multiple filterable collapse-tags data-test="billing-model-filter">
  <ElOption v-for="model in models" :key="model.id" :label="model.display_name" :value="model.id" />
</ElSelect>
<ElSelect v-model="selectedApiKeyIds" multiple filterable collapse-tags data-test="billing-api-key-filter">
  <ElOption
    v-for="key in apiKeys"
    :key="key.id"
    :data-test="`billing-api-key-option-${String(key.id)}`"
    :label="auth.isAdmin ? `${key.name} · #${String(key.id)}` : key.name"
    :value="key.id"
  />
</ElSelect>
```

Store dates as `Date[]`, display `Intl.DateTimeFormat().resolvedOptions().timeZone`, validate ordering and the 366-day maximum in the view, and convert only with `toISOString()` at the API boundary. Use separate abort controllers for catalog and aggregate requests, disable Apply during aggregate loading, and make a catalog error non-blocking. Both roles render requests, failure rate, tokens, billed amount, and average latency; only administrators render upstream cost and gross profit. Import the Element Plus CSS modules for date-picker, select, option, table, pagination, empty, alert, skeleton, and result components.

- [ ] **Step 4: Render accessible charts and tables**

```ts
const trendOption = computed<BillingChartOption>(() => ({
  aria: { enabled: true },
  legend: { data: auth.isAdmin
    ? ['请求数', '失败数', '用户费用', '成本', '毛利']
    : ['请求数', '失败数', '费用'] },
  xAxis: { type: 'category', data: points.value.map((point) => point.date) },
  yAxis: [{ type: 'value' }, { type: 'value' }],
  series: [
    { name: '请求数', type: 'bar', data: points.value.map((point) => point.requests) },
    { name: '失败数', type: 'bar', data: points.value.map((point) => point.failed_requests) },
    { name: auth.isAdmin ? '用户费用' : '费用', type: 'line', yAxisIndex: 1,
      data: points.value.map((point) => point.user_cost) },
    ...(auth.isAdmin ? [
      { name: '成本', type: 'line', yAxisIndex: 1,
        data: adminPoints.value.map((point) => point.cost_amount) },
      { name: '毛利', type: 'line', yAxisIndex: 1,
        data: adminPoints.value.map((point) => point.gross_profit) },
    ] : []),
  ],
}))
```

Register the same ECharts modules as `DashboardView.vue`. Preserve backend Decimal ordering and use `rows.slice(0, 20)` for each horizontal bar chart; never sort amount strings in the browser. Administrators get provider/model/API-key charts with billed amount, upstream cost, and gross profit; regular users get model/API-key charts with billed amount only. Place an Element Plus paginated table below each chart with the permitted columns and 50 rows per page; use `ElEmpty` for empty ranges so charts are not the sole carrier of data.

- [ ] **Step 5: Run the green page test**

Run: `npm --prefix frontend run test -- tests/billing-statistics.spec.ts`

Expected: PASS.

- [ ] **Step 6: Add browser tests for both roles and responsive layout**

```ts
test('管理员看到供应商成本，普通用户只看到自己的费用', async ({ page }) => {
  await installBillingRoutes(page, adminUser)
  await page.goto('billing-statistics')
  await expect(page.getByTestId('billing-provider-filter')).toBeVisible()
  await expect(page.getByText('成本')).toBeVisible()

  await installBillingRoutes(page, regularUser)
  await page.reload()
  await expect(page.getByTestId('billing-provider-filter')).toHaveCount(0)
  await expect(page.getByText('成本')).toHaveCount(0)
  await expect(page.getByText('生产密钥 · #4')).toHaveCount(0)
})

test('普通用户在窄屏可以应用多选且页面没有横向溢出', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await installBillingRoutes(page, regularUser)
  await page.goto('billing-statistics')
  await page.getByLabel('打开导航菜单').click()
  await page.getByRole('menuitem', { name: '账单统计' }).click()
  await page.getByTestId('billing-model-filter').click()
  await page.getByRole('option', { name: 'GPT 4.1' }).click()
  await page.getByTestId('billing-apply').click()
  await expect.poll(() => page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )).toBe(0)
})
```

Intercept `/auth/me`, both statistics endpoints, and the role-appropriate catalog endpoints in `installBillingRoutes`.

Run: `npm --prefix frontend run e2e -- frontend/e2e/billing-statistics.spec.ts`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/BillingStatisticsView.vue frontend/tests/billing-statistics.spec.ts frontend/e2e/billing-statistics.spec.ts
git commit -m "feat: add billing statistics page"
```

### Task 5: Validate the complete feature

**Files:**
- Modify only files proven defective by the checks below.

**Interfaces:**
- Produces CI evidence for the migration, API, routing, filters, and charts.

- [ ] **Step 1: Run focused backend and frontend regressions**

Run:

```bash
uv run pytest tests/integration/admin/test_billing_statistics.py tests/integration/admin/test_dashboard.py tests/integration/migrations/test_0017_billing_statistics_indexes.py -q
npm --prefix frontend run test -- tests/billing-statistics.spec.ts tests/router.spec.ts tests/admin-layout.spec.ts tests/dashboard.spec.ts
```

Expected: PASS.

- [ ] **Step 2: Run CI-equivalent validation**

Run:

```bash
uv run alembic upgrade head
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src scripts
uv run pytest -W error --cov=ai_gateway --cov-report=term-missing --cov-fail-under=90
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm exec --prefix frontend -- playwright install --with-deps chromium
export E2E_ADMIN_EMAIL='console-e2e@example.com'
export E2E_ADMIN_PASSWORD='billing-statistics-ci-password-2026'
npm --prefix frontend run e2e
unset E2E_ADMIN_EMAIL E2E_ADMIN_PASSWORD
docker compose -f compose.yaml config --quiet
docker compose -f example/compose.yaml config --quiet
docker build -t lean-ai-gateway:test .
git diff --check
```

Expected: every command exits with status 0; report an unrelated pre-existing failure separately.

- [ ] **Step 3: Commit only validation-proven corrections**

```bash
git add src/ai_gateway/admin/billing_statistics.py src/ai_gateway/db/models/audit.py \
  src/ai_gateway/main.py frontend/src/api/billingStatistics.ts frontend/src/api/types.ts \
  frontend/src/router/index.ts frontend/src/layouts/AdminLayout.vue \
  frontend/src/views/BillingStatisticsView.vue
git commit -m "fix: complete billing statistics validation"
```
