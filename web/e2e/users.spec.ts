import { test, expect } from '@playwright/test'

test.describe('User Management', () => {
  test.beforeEach(async ({ page }) => {
    // Setup authentication mocks
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

    // Login
    await page.goto('/login')
    await page.locator('input[type="text"]').first().fill('admin@example.com')
    await page.locator('input[type="password"]').fill('password123')
    await page.locator('button').first().click()
    await page.waitForURL('/dashboard')
  })

  test('should show user list', async ({ page }) => {
    await page.route('**/api/users*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          users: [
            { id: 1, email: 'admin@example.com', role: 'ADMIN', balance: 100, disabled: false },
            { id: 2, email: 'user@example.com', role: 'USER', balance: 50, disabled: false }
          ],
          total: 2
        })
      })
    })

    await page.goto('/users')
    await expect(page.locator('.el-table')).toBeVisible()
    await expect(page.locator('text=admin@example.com')).toBeVisible()
    await expect(page.locator('text=user@example.com')).toBeVisible()
  })

  test('should open create user dialog', async ({ page }) => {
    await page.route('**/api/users*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ users: [], total: 0 })
      })
    })

    await page.goto('/users')
    await page.click('text=创建')

    await expect(page.locator('.el-dialog')).toBeVisible()
    await expect(page.locator('text=创建用户')).toBeVisible()
  })

  test('should create new user', async ({ page }) => {
    await page.route('**/api/users*', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ users: [], total: 0 })
        })
      } else if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 3, email: 'new@example.com', role: 'USER' })
        })
      }
    })

    await page.goto('/users')
    await page.click('text=创建')

    await page.locator('.el-dialog input[type="text"]').first().fill('new@example.com')
    await page.locator('.el-dialog input[type="password"]').fill('password123')
    await page.locator('.el-dialog button:has-text("保存")').click()

    await expect(page.locator('.el-message--success')).toBeVisible()
  })

  test('should edit user', async ({ page }) => {
    await page.route('**/api/users*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          users: [
            { id: 2, email: 'user@example.com', role: 'USER', balance: 50 }
          ],
          total: 1
        })
      })
    })

    await page.route('**/api/users/2', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 2, email: 'user@example.com', role: 'USER', balance: 50 })
        })
      } else if (route.request().method() === 'PUT') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: 2, role: 'ADMIN' })
        })
      }
    })

    await page.goto('/users')
    await page.click('text=编辑')

    await expect(page.locator('.el-dialog')).toBeVisible()
    await expect(page.locator('text=编辑用户')).toBeVisible()
  })

  test('should delete user with confirmation', async ({ page }) => {
    await page.route('**/api/users*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          users: [
            { id: 2, email: 'user@example.com', role: 'USER', balance: 50 }
          ],
          total: 1
        })
      })
    })

    await page.route('**/api/users/2', async (route) => {
      if (route.request().method() === 'DELETE') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({})
        })
      }
    })

    await page.goto('/users')
    await page.click('button:has-text("删除")')

    // Confirm deletion
    await expect(page.locator('.el-message-box')).toBeVisible()
    await page.click('.el-message-box button:has-text("确认")')

    await expect(page.locator('.el-message--success')).toBeVisible()
  })
})

test.describe('Provider Management', () => {
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

  test('should show provider list', async ({ page }) => {
    await page.route('**/api/providers*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          providers: [
            { id: 1, name: 'OpenAI', base_url: 'https://api.openai.com', type: 'OpenAI' }
          ],
          total: 1
        })
      })
    })

    await page.goto('/providers')
    await expect(page.locator('.el-table')).toBeVisible()
    await expect(page.locator('text=OpenAI')).toBeVisible()
  })

  test('should open create provider dialog', async ({ page }) => {
    await page.route('**/api/providers*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ providers: [], total: 0 })
      })
    })

    await page.goto('/providers')
    await page.click('text=创建')

    await expect(page.locator('.el-dialog')).toBeVisible()
    await expect(page.locator('text=创建提供商')).toBeVisible()
  })

  test('should load models from provider', async ({ page }) => {
    await page.route('**/api/providers*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          providers: [
            { id: 1, name: 'OpenAI', base_url: 'https://api.openai.com', type: 'OpenAI' }
          ],
          total: 1
        })
      })
    })

    await page.route('**/api/providers/1/load-models', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ models: ['gpt-4', 'gpt-3.5-turbo'] })
      })
    })

    await page.goto('/providers')
    await page.click('button:has-text("加载模型")')

    await expect(page.locator('.el-message--success')).toBeVisible()
  })
})