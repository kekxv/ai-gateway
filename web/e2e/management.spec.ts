import { test, expect } from '@playwright/test'

test.describe('API Key Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          token: 'mock-token',
          user: { id: 1, email: 'admin@example.com', role: 'ADMIN' }
        })
      })
    })

    await page.route('**/api/users/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, email: 'admin@example.com', role: 'ADMIN' })
      })
    })

    await page.goto('/login')
    await page.locator('input[type="text"]').first().fill('admin@example.com')
    await page.locator('input[type="password"]').fill('password123')
    await page.locator('button').first().click()
    await page.waitForURL('/dashboard')
  })

  test('should show API key list', async ({ page }) => {
    await page.route('**/api/keys*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          keys: [
            { id: 1, name: 'Test Key', key: 'sk-1234567890abcdef', enabled: true }
          ],
          total: 1
        })
      })
    })

    await page.goto('/keys')
    await expect(page.locator('.el-table')).toBeVisible()
    await expect(page.locator('text=Test Key')).toBeVisible()
  })

  test('should open create API key dialog', async ({ page }) => {
    await page.route('**/api/keys*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ keys: [], total: 0 })
      })
    })

    await page.goto('/keys')
    await page.click('text=创建')

    await expect(page.locator('.el-dialog')).toBeVisible()
    await expect(page.locator('text=创建API Key')).toBeVisible()
  })

  test('should create new API key and show key dialog', async ({ page }) => {
    await page.route('**/api/keys*', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ keys: [], total: 0 })
        })
      } else if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 1, key: 'sk-new-key-generated' })
        })
      }
    })

    await page.goto('/keys')
    await page.click('text=创建')

    await page.locator('.el-dialog input').first().fill('New Key')
    await page.locator('.el-dialog button:has-text("保存")').click()

    // Should show new key in a dialog
    await expect(page.locator('.el-dialog')).toBeVisible()
    await expect(page.locator('text=sk-new-key-generated')).toBeVisible()
  })
})

test.describe('Log Viewing', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          token: 'mock-token',
          user: { id: 1, email: 'admin@example.com', role: 'ADMIN' }
        })
      })
    })

    await page.route('**/api/users/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, email: 'admin@example.com', role: 'ADMIN' })
      })
    })

    await page.goto('/login')
    await page.locator('input[type="text"]').first().fill('admin@example.com')
    await page.locator('input[type="password"]').fill('password123')
    await page.locator('button').first().click()
    await page.waitForURL('/dashboard')
  })

  test('should show log list', async ({ page }) => {
    await page.route('**/api/logs*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          logs: [
            { id: 1, model: 'gpt-4', provider: 'OpenAI', status: 'success', latency_ms: 500 }
          ],
          total: 1
        })
      })
    })

    await page.goto('/logs')
    await expect(page.locator('.el-table')).toBeVisible()
    await expect(page.locator('text=gpt-4')).toBeVisible()
  })

  test('should filter logs by model', async ({ page }) => {
    await page.route('**/api/logs*', async (route) => {
      const url = new URL(route.request().url())
      const model = url.searchParams.get('model')

      if (model === 'gpt-4') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            logs: [
              { id: 1, model: 'gpt-4', provider: 'OpenAI', status: 'success' }
            ],
            total: 1
          })
        })
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            logs: [
              { id: 1, model: 'gpt-4', provider: 'OpenAI', status: 'success' },
              { id: 2, model: 'gpt-3.5', provider: 'OpenAI', status: 'success' }
            ],
            total: 2
          })
        })
      }
    })

    await page.goto('/logs')

    // Filter by model
    await page.locator('input[placeholder="Model"]').fill('gpt-4')
    await page.click('button:has-text("搜索")')

    // Should only show filtered logs
    await expect(page.locator('.el-table')).toBeVisible()
  })

  test('should show log detail', async ({ page }) => {
    await page.route('**/api/logs*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          logs: [
            { id: 1, model: 'gpt-4', provider: 'OpenAI', status: 'success' }
          ],
          total: 1
        })
      })
    })

    await page.route('**/api/logs/1', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          model: 'gpt-4',
          provider: 'OpenAI',
          status: 'success',
          request: '{"prompt": "Hello"}',
          response: '{"text": "World"}'
        })
      })
    })

    await page.goto('/logs')
    await page.click('button:has-text("详情")')

    await expect(page.locator('.el-dialog')).toBeVisible()
    await expect(page.locator('text=Log Detail')).toBeVisible()
  })
})

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          token: 'mock-token',
          user: { id: 1, email: 'admin@example.com', role: 'ADMIN' }
        })
      })
    })

    await page.route('**/api/users/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, email: 'admin@example.com', role: 'ADMIN' })
      })
    })

    await page.goto('/login')
    await page.locator('input[type="text"]').first().fill('admin@example.com')
    await page.locator('input[type="password"]').fill('password123')
    await page.locator('button').first().click()
    await page.waitForURL('/dashboard')
  })

  test('should show stats cards', async ({ page }) => {
    await page.route('**/api/stats*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          totalRequests: 1000,
          totalTokens: 50000,
          totalCost: 10.5,
          byProvider: [],
          byModel: [],
          dailyUsage: []
        })
      })
    })

    await page.goto('/dashboard')

    await expect(page.locator('.el-card')).toBeVisible()
    await expect(page.locator('text=1000')).toBeVisible()
    await expect(page.locator('text=总请求数')).toBeVisible()
  })

  test('should show daily usage chart', async ({ page }) => {
    await page.route('**/api/stats*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          totalRequests: 1000,
          totalTokens: 50000,
          totalCost: 10.5,
          byProvider: [],
          byModel: [],
          dailyUsage: [
            { date: '2024-01-01', requests: 100, tokens: 5000 },
            { date: '2024-01-02', requests: 200, tokens: 10000 }
          ]
        })
      })
    })

    await page.goto('/dashboard')

    await expect(page.locator('text=每日使用量')).toBeVisible()
  })
})

test.describe('Profile Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          token: 'mock-token',
          user: { id: 1, email: 'admin@example.com', role: 'ADMIN' }
        })
      })
    })

    await page.route('**/api/users/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, email: 'admin@example.com', role: 'ADMIN', balance: 100, totp_enabled: false })
      })
    })

    await page.goto('/login')
    await page.locator('input[type="text"]').first().fill('admin@example.com')
    await page.locator('input[type="password"]').fill('password123')
    await page.locator('button').first().click()
    await page.waitForURL('/dashboard')
  })

  test('should show user profile info', async ({ page }) => {
    await page.goto('/profile')

    await expect(page.locator('text=admin@example.com')).toBeVisible()
    await expect(page.locator('text=ADMIN')).toBeVisible()
  })

  test('should show change password form', async ({ page }) => {
    await page.goto('/profile')

    await expect(page.locator('text=修改密码')).toBeVisible()
    await expect(page.locator('input[type="password"]').first()).toBeVisible()
  })

  test('should show TOTP setup button when not enabled', async ({ page }) => {
    await page.goto('/profile')

    await expect(page.locator('button:has-text("设置TOTP")')).toBeVisible()
  })

  test('should change password', async ({ page }) => {
    await page.route('**/api/users/me/change-password', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({})
      })
    })

    await page.goto('/profile')

    // Fill password form
    await page.locator('input[placeholder*="当前密码"]').fill('oldpassword')
    await page.locator('input[placeholder*="新密码"]').fill('newpassword123')
    await page.locator('input[placeholder*="确认密码"]').fill('newpassword123')
    await page.click('button:has-text("保存")')

    await expect(page.locator('.el-message--success')).toBeVisible()
  })
})