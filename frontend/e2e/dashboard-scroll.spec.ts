import { expect, test } from '@playwright/test'

const adminUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin',
  is_active: true,
  totp_enabled: false,
  created_at: '2026-07-31T00:00:00',
  updated_at: '2026-07-31T00:00:00',
}

const dashboardSummary = {
  users_total: 1,
  active_api_keys: 1,
  providers: { total: 1, enabled: 1 },
  models: { total: 1, enabled: 1 },
  routes: { total: 1, enabled: 1, unavailable: 0 },
  requests_24h: 12,
  failed_requests_24h: 0,
  prompt_tokens_24h: 652,
  completion_tokens_24h: 380,
  cache_read_tokens_24h: 0,
  cache_write_tokens_24h: 0,
  total_tokens_24h: 1_032,
  cost_24h: '0',
  cost_amount_24h: '0',
  gross_profit_24h: '0',
  average_latency_ms_24h: 42,
  total_requests: 12,
  total_cost: '0',
  total_cost_amount: '0',
  total_gross_profit: '0',
  total_prompt_tokens: 652,
  total_completion_tokens: 380,
  daily_usage: [],
  top_models: [
    {
      model_name: 'deepseek-v4-flash',
      display_name: 'deepseek-v4-flash',
      requests: 12,
      prompt_tokens: 652,
      completion_tokens: 380,
      cost: '0',
      cost_amount: '0',
    },
  ],
  provider_stats: [],
}

test('控制台概览只滚动主内容区，页面外壳保持在视口内', async ({ page }) => {
  await page.setViewportSize({ width: 1_200, height: 720 })
  await page.addInitScript(() => {
    window.localStorage.setItem('gateway.access_token', 'e2e-access-token')
    window.localStorage.setItem('gateway.refresh_token', 'e2e-refresh-token')
  })
  await page.route('**/auth/me', (route) => route.fulfill({ json: adminUser }))
  await page.route('**/admin/dashboard/summary**', (route) =>
    route.fulfill({ json: dashboardSummary }),
  )

  await page.goto('')
  await expect(page.getByRole('heading', { level: 1, name: '控制台概览' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: '热门模型' })).toBeVisible()

  const layout = await page.evaluate(() => {
    const main = document.querySelector<HTMLElement>('.admin-main')
    const shell = document.querySelector<HTMLElement>('.admin-shell')
    if (main === null || shell === null) throw new Error('未找到控制台布局')
    return {
      documentClientHeight: document.documentElement.clientHeight,
      documentScrollHeight: document.documentElement.scrollHeight,
      mainClientHeight: main.clientHeight,
      mainScrollHeight: main.scrollHeight,
      mainScrollWidth: main.scrollWidth,
      mainClientWidth: main.clientWidth,
      shellTop: shell.getBoundingClientRect().top,
    }
  })

  expect(layout.documentScrollHeight).toBe(layout.documentClientHeight)
  expect(layout.mainScrollHeight).toBeGreaterThan(layout.mainClientHeight)
  expect(layout.mainScrollWidth).toBe(layout.mainClientWidth)
  expect(layout.shellTop).toBe(0)

  await page.evaluate(() => {
    window.scrollTo(0, 10_000)
  })
  expect(await page.evaluate(() => window.scrollY)).toBe(0)
  expect(
    await page.locator('.admin-shell').evaluate((shell) => shell.getBoundingClientRect().top),
  ).toBe(0)
})

test('图标模式侧栏只允许纵向滚动', async ({ page }) => {
  await page.setViewportSize({ width: 1_199, height: 420 })
  await page.addInitScript(() => {
    window.localStorage.setItem('gateway.access_token', 'e2e-access-token')
    window.localStorage.setItem('gateway.refresh_token', 'e2e-refresh-token')
  })
  await page.route('**/auth/me', (route) => route.fulfill({ json: adminUser }))
  await page.route('**/admin/dashboard/summary**', (route) =>
    route.fulfill({ json: dashboardSummary }),
  )

  await page.goto('')
  await expect(page.locator('.admin-menu.el-menu--collapse')).toBeVisible()

  const sidebar = await page.locator('.admin-sidebar').evaluate((element) => ({
    clientHeight: element.clientHeight,
    clientWidth: element.clientWidth,
    scrollHeight: element.scrollHeight,
    scrollWidth: element.scrollWidth,
  }))

  expect(sidebar.scrollHeight).toBeGreaterThan(sidebar.clientHeight)
  expect(sidebar.scrollWidth).toBe(sidebar.clientWidth)
})
