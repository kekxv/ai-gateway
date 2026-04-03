import { test, expect } from '@playwright/test'

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('should show login page', async ({ page }) => {
    await expect(page).toHaveURL('/login')
    await expect(page.locator('h1')).toContainText('AI Gateway')
  })

  test('should show login form elements', async ({ page }) => {
    await page.goto('/login')

    // Check for email input
    await expect(page.locator('input[type="text"]').first()).toBeVisible()

    // Check for password input
    await expect(page.locator('input[type="password"]')).toBeVisible()

    // Check for login button
    await expect(page.locator('button')).toContainText('登录')
  })

  test('should validate email field', async ({ page }) => {
    await page.goto('/login')

    // Try to submit with empty email
    await page.locator('input[type="password"]').fill('password123')
    await page.locator('button').first().click()

    // Should show validation error
    await expect(page.locator('.el-form-item__error')).toBeVisible()
  })

  test('should validate password field', async ({ page }) => {
    await page.goto('/login')

    // Try to submit with empty password
    await page.locator('input[type="text"]').first().fill('test@example.com')
    await page.locator('button').first().click()

    // Should show validation error
    await expect(page.locator('.el-form-item__error')).toBeVisible()
  })

  test('should redirect to dashboard after successful login', async ({ page }) => {
    // Mock the login API response
    await page.route('**/api/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          token: 'mock-token',
          user: {
            id: 1,
            email: 'admin@example.com',
            role: 'ADMIN'
          }
        })
      })
    })

    // Mock the current user API
    await page.route('**/api/users/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          email: 'admin@example.com',
          role: 'ADMIN'
        })
      })
    })

    await page.goto('/login')

    // Fill in the form
    await page.locator('input[type="text"]').first().fill('admin@example.com')
    await page.locator('input[type="password"]').fill('password123')
    await page.locator('button').first().click()

    // Wait for navigation
    await page.waitForURL('/dashboard', { timeout: 10000 })
    await expect(page).toHaveURL('/dashboard')
  })

  test('should show error on failed login', async ({ page }) => {
    // Mock failed login response
    await page.route('**/api/auth/login', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Invalid credentials'
        })
      })
    })

    await page.goto('/login')

    await page.locator('input[type="text"]').first().fill('wrong@example.com')
    await page.locator('input[type="password"]').fill('wrongpassword')
    await page.locator('button').first().click()

    // Should show error message
    await expect(page.locator('.el-alert--error')).toBeVisible()
  })

  test('should show TOTP field when required', async ({ page }) => {
    // Mock TOTP required response
    await page.route('**/api/auth/login', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'TOTP verification required'
        })
      })
    })

    await page.goto('/login')

    await page.locator('input[type="text"]').first().fill('user@example.com')
    await page.locator('input[type="password"]').fill('password123')
    await page.locator('button').first().click()

    // Should show TOTP input
    await expect(page.locator('input[placeholder*="TOTP"]')).toBeVisible()
  })
})

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    // Mock authentication
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

  test('should show sidebar menu', async ({ page }) => {
    await expect(page.locator('aside')).toBeVisible()
  })

  test('should navigate to providers page', async ({ page }) => {
    await page.click('text=提供商管理')
    await expect(page).toHaveURL('/providers')
  })

  test('should navigate to channels page', async ({ page }) => {
    await page.click('text=渠道管理')
    await expect(page).toHaveURL('/channels')
  })

  test('should navigate to models page', async ({ page }) => {
    await page.click('text=模型管理')
    await expect(page).toHaveURL('/models')
  })

  test('should navigate to API keys page', async ({ page }) => {
    await page.click('text=API Key管理')
    await expect(page).toHaveURL('/keys')
  })

  test('should navigate to logs page', async ({ page }) => {
    await page.click('text=日志查看')
    await expect(page).toHaveURL('/logs')
  })

  test('should navigate to profile page', async ({ page }) => {
    await page.click('text=个人资料')
    await expect(page).toHaveURL('/profile')
  })

  test('should show users page for admin', async ({ page }) => {
    await expect(page.locator('text=用户管理')).toBeVisible()
    await page.click('text=用户管理')
    await expect(page).toHaveURL('/users')
  })
})

test.describe('Language Switch', () => {
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

  test('should switch to English', async ({ page }) => {
    await page.selectOption('select', 'en')

    // Menu should show English text
    await expect(page.locator('text=Providers')).toBeVisible()
    await expect(page.locator('text=Channels')).toBeVisible()
  })

  test('should switch to Chinese', async ({ page }) => {
    // First switch to English
    await page.selectOption('select', 'en')
    await expect(page.locator('text=Providers')).toBeVisible()

    // Switch back to Chinese
    await page.selectOption('select', 'zh')
    await expect(page.locator('text=提供商管理')).toBeVisible()
  })
})

test.describe('Logout', () => {
  test('should logout successfully', async ({ page }) => {
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

    // Click logout button
    await page.click('text=退出登录')

    // Should redirect to login
    await page.waitForURL('/login')
    await expect(page).toHaveURL('/login')
  })
})