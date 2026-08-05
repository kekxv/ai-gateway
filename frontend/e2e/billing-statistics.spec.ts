import { expect, test } from '@playwright/test'

const adminUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin',
  is_active: true,
  totp_enabled: false,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
}

const regularUser = { ...adminUser, id: 2, email: 'user@example.com', role: 'user' }

const totals = {
  requests: 3,
  failed_requests: 1,
  prompt_tokens: 20,
  completion_tokens: 10,
  cache_read_tokens: 0,
  cache_write_tokens: 0,
  user_cost: '1.25000000',
  average_latency_ms: 100,
}

const dimension = { id: 2, name: '模型 A', ...totals }

test('账单统计按角色显示对应筛选条件与财务字段', async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('gateway.access_token', 'e2e-access-token')
    window.localStorage.setItem('gateway.refresh_token', 'e2e-refresh-token')
  })
  await page.route('**/auth/me', (route) => route.fulfill({ json: adminUser }))
  await page.route('**/admin/dashboard/summary**', (route) => route.abort())
  await page.route('**/admin/providers', (route) => route.fulfill({ json: [{ id: 1, name: '供应商 A' }] }))
  await page.route('**/admin/models', (route) => route.fulfill({ json: [{ id: 2, display_name: '模型 A', canonical_name: 'model-a' }] }))
  await page.route('**/admin/api-keys', (route) => route.fulfill({ json: [{ id: 3, name: '管理密钥', user_email: 'hidden@example.com' }] }))
  await page.route('**/admin/billing-statistics**', (route) => route.fulfill({ json: {
    totals: { ...totals, cost_amount: '0.80000000', gross_profit: '0.45000000' },
    daily_usage: [{ date: '2026-08-01', ...totals, cost_amount: '0.80000000', gross_profit: '0.45000000' }],
    provider_stats: [{ id: 1, name: '供应商 A', ...totals, cost_amount: '0.80000000', gross_profit: '0.45000000' }],
    model_stats: [{ ...dimension, cost_amount: '0.80000000', gross_profit: '0.45000000' }],
    api_key_stats: [{ ...dimension, id: 3, name: '管理密钥', cost_amount: '0.80000000', gross_profit: '0.45000000' }],
  } }))

  await page.goto('')
  await page.getByText('账单统计', { exact: true }).first().click()
  await expect(page.getByRole('heading', { level: 1, name: '账单统计' })).toBeVisible()
  await expect(page.getByTestId('provider-filter')).toBeVisible()
  await expect(page.getByTestId('internal-cost-kpi')).toContainText('¥0.80000000')
  await expect(page.getByTestId('gross-profit-kpi')).toContainText('¥0.45000000')

  await page.unrouteAll()
  await page.route('**/auth/me', (route) => route.fulfill({ json: regularUser }))
  await page.route('**/me/dashboard/summary**', (route) => route.abort())
  await page.route('**/user/models', (route) => route.fulfill({ json: [{ id: 2, display_name: '模型 A', canonical_name: 'model-a' }] }))
  await page.route('**/user/api-keys', (route) => route.fulfill({ json: [{ id: 4, name: '我的密钥', user_email: 'hidden@example.com' }] }))
  await page.route('**/user/billing-statistics**', (route) => route.fulfill({ json: {
    totals,
    daily_usage: [{ date: '2026-08-01', ...totals }],
    model_stats: [dimension],
    api_key_stats: [{ ...dimension, id: 4, name: '我的密钥' }],
  } }))
  await page.goto('')
  await page.getByText('账单统计', { exact: true }).first().click()
  await expect(page.getByRole('heading', { level: 1, name: '账单统计' })).toBeVisible()
  await expect(page.getByTestId('provider-filter')).toHaveCount(0)
  await expect(page.getByTestId('internal-cost-kpi')).toHaveCount(0)
  await expect(page.getByTestId('gross-profit-kpi')).toHaveCount(0)
  await expect(page.getByText('hidden@example.com')).toHaveCount(0)
})
