import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Locator, type Page } from '@playwright/test'

const adminEmail = process.env.E2E_ADMIN_EMAIL
const adminPassword = process.env.E2E_ADMIN_PASSWORD

// The smoke journey renders a one-time API key. Disable artifact capture for this
// file so the secret cannot be persisted in traces, screenshots, or video.
test.use({ screenshot: 'off', trace: 'off', video: 'off' })

interface CreatedEntities {
  apiKeyId?: number
  modelId?: number
  providerId?: number
  routeId?: number
  userId?: number
}

interface CleanupRequest {
  body?: Record<string, unknown>
  method: 'DELETE' | 'PATCH'
  path: string
}

interface EntityNames {
  apiKey: string
  model: string
  provider: string
  user: string
}

function requireCredentials(): { email: string; password: string } {
  if (adminEmail === undefined || adminPassword === undefined) {
    throw new Error('E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD are required')
  }
  return { email: adminEmail, password: adminPassword }
}

async function login(page: Page): Promise<void> {
  const credentials = requireCredentials()
  await page.goto('login')
  await page.getByTestId('email').fill(credentials.email)
  await page.getByTestId('password').fill(credentials.password)
  await page.getByTestId('submit').click()
  await expect(page.getByRole('heading', { level: 1, name: '控制台概览' })).toBeVisible()
}

async function registerFirstAdministrator(page: Page): Promise<void> {
  const credentials = requireCredentials()
  await page.goto('register')
  await page.getByTestId('register-email').fill(credentials.email)
  await page.getByTestId('register-password').fill(credentials.password)
  await page.getByTestId('register-password-confirm').fill(credentials.password)
  await page.getByTestId('register-submit').click()
  await expect(page.getByRole('heading', { level: 1, name: '控制台概览' })).toBeVisible()
}

async function numericId(locator: Locator, prefix: string): Promise<number> {
  const attribute = await locator.getAttribute('data-test')
  if (attribute === null || !attribute.startsWith(prefix)) {
    throw new Error(`Expected ${prefix}<id> data-test attribute`)
  }
  const id = Number(attribute.slice(prefix.length))
  if (!Number.isInteger(id) || id < 1) throw new Error(`Invalid entity id for ${prefix}`)
  return id
}

async function setSwitch(locator: Locator, checked: boolean): Promise<void> {
  const input = locator.locator('input[type="checkbox"]')
  if ((await input.isChecked()) !== checked) await locator.click()
  await expect(input).toBeChecked({ checked })
}

async function cleanupRequest(page: Page, request: CleanupRequest): Promise<number> {
  return page.evaluate(async ({ body, method, path }) => {
    const token = window.sessionStorage.getItem('gateway.access_token')
    if (token === null) return 401
    const response = await window.fetch(path, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body === undefined ? {} : { 'content-type': 'application/json' }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
    return response.status
  }, request)
}

async function lookupEntityId(
  page: Page,
  path: string,
  field: string,
  value: string | number,
): Promise<number | undefined> {
  return page.evaluate(async ({ field, path, value }) => {
    const token = window.sessionStorage.getItem('gateway.access_token')
    if (token === null) return undefined
    const response = await window.fetch(path, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) return undefined
    const payload: unknown = await response.json()
    if (!Array.isArray(payload)) return undefined
    const items: unknown[] = payload
    const match = items.find((item) => {
      if (typeof item !== 'object' || item === null) return false
      return (item as Record<string, unknown>)[field] === value
    })
    if (typeof match !== 'object' || match === null) return undefined
    const id = (match as Record<string, unknown>).id
    return typeof id === 'number' ? id : undefined
  }, { field, path, value })
}

async function deleteOrDisable(page: Page, path: string, fallbackBody: Record<string, unknown>) {
  const status = await cleanupRequest(page, { method: 'DELETE', path })
  if (status >= 200 && status < 300) return
  const fallbackStatus = await cleanupRequest(page, {
    body: fallbackBody,
    method: 'PATCH',
    path,
  })
  if (fallbackStatus < 200 || fallbackStatus >= 300) throw new Error('cleanup request failed')
}

async function expectSafeCondition(
  check: () => Promise<boolean>,
  message: string,
): Promise<void> {
  await expect.poll(check, { message }).toBe(true)
}

async function secretIsVisibleAndNonEmpty(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const element = document.querySelector<HTMLElement>('[data-test="one-time-secret"]')
    if (element === null || element.textContent.trim() === '') return false
    const style = window.getComputedStyle(element)
    return style.display !== 'none' && style.visibility !== 'hidden' && element.getClientRects().length > 0
  })
}

async function secretNodeIsAbsent(page: Page): Promise<boolean> {
  return page.evaluate(
    () => document.querySelector('[data-test="one-time-secret"]') === null,
  )
}

async function localStorageIsEmpty(page: Page): Promise<boolean> {
  return page.evaluate(() => window.localStorage.length === 0)
}

async function sessionStorageHasOnlyTokens(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const keys = Object.keys(window.sessionStorage).sort()
    return (
      keys.length === 2 &&
      keys[0] === 'gateway.access_token' &&
      keys[1] === 'gateway.refresh_token'
    )
  })
}

async function closeSecretDialogIfPresent(page: Page): Promise<void> {
  const present = await page.evaluate(
    () => document.querySelector('[data-test="one-time-secret"]') !== null,
  )
  if (!present) return
  await page.getByTestId('secret-acknowledged').click()
  await page.getByTestId('secret-confirm-close').click()
}

async function attemptCleanup(
  failures: string[],
  stage: string,
  operation: () => Promise<void>,
): Promise<void> {
  try {
    await operation()
  } catch {
    failures.push(stage)
  }
}

async function recoverEntityId(
  failures: string[],
  stage: string,
  operation: () => Promise<number | undefined>,
  assign: (id: number) => void,
): Promise<void> {
  try {
    const id = await operation()
    if (id !== undefined) assign(id)
  } catch {
    failures.push(stage)
  }
}

async function cleanup(page: Page, entities: CreatedEntities, names: EntityNames): Promise<void> {
  const failures: string[] = []
  await attemptCleanup(failures, 'secret dialog close', () => closeSecretDialogIfPresent(page))
  await attemptCleanup(failures, 'secret DOM removal verification', async () => {
    await expectSafeCondition(() => secretNodeIsAbsent(page), 'Secret node was not removed')
  })
  await attemptCleanup(failures, 'local storage verification', async () => {
    await expectSafeCondition(() => localStorageIsEmpty(page), 'Local storage was not empty')
  })
  await attemptCleanup(failures, 'session storage verification', async () => {
    await expectSafeCondition(
      () => sessionStorageHasOnlyTokens(page),
      'Session storage keys were not the exact allowlist',
    )
  })
  if (entities.apiKeyId === undefined) {
    await recoverEntityId(
      failures,
      'API key ID recovery',
      () => lookupEntityId(page, '/admin/api-keys', 'name', names.apiKey),
      (id) => {
        entities.apiKeyId = id
      },
    )
  }
  if (entities.modelId === undefined) {
    await recoverEntityId(
      failures,
      'model ID recovery',
      () => lookupEntityId(page, '/admin/models', 'canonical_name', names.model),
      (id) => {
        entities.modelId = id
      },
    )
  }
  if (entities.providerId === undefined) {
    await recoverEntityId(
      failures,
      'provider ID recovery',
      () => lookupEntityId(page, '/admin/providers', 'name', names.provider),
      (id) => {
        entities.providerId = id
      },
    )
  }
  if (entities.userId === undefined) {
    await recoverEntityId(
      failures,
      'user ID recovery',
      () => lookupEntityId(page, '/admin/users', 'email', names.user),
      (id) => {
        entities.userId = id
      },
    )
  }
  if (entities.modelId !== undefined && entities.routeId === undefined) {
    await recoverEntityId(
      failures,
      'route ID recovery',
      () =>
        lookupEntityId(
          page,
          `/admin/model-routes?model_id=${String(entities.modelId)}`,
          'upstream_model',
          'e2e-original-model',
        ),
      (id) => {
        entities.routeId = id
      },
    )
  }
  if (entities.apiKeyId !== undefined) {
    await attemptCleanup(failures, 'API key cleanup', () =>
      deleteOrDisable(page, `/admin/api-keys/${String(entities.apiKeyId)}`, {
        is_active: false,
      }),
    )
  }
  if (entities.routeId !== undefined) {
    await attemptCleanup(failures, 'route cleanup', () =>
      deleteOrDisable(page, `/admin/model-routes/${String(entities.routeId)}`, {
        enabled: false,
      }),
    )
  }
  if (entities.modelId !== undefined) {
    await attemptCleanup(failures, 'model cleanup', () =>
      deleteOrDisable(page, `/admin/models/${String(entities.modelId)}`, { enabled: false }),
    )
  }
  if (entities.providerId !== undefined) {
    await attemptCleanup(failures, 'provider cleanup', () =>
      deleteOrDisable(page, `/admin/providers/${String(entities.providerId)}`, {
        enabled: false,
      }),
    )
  }
  if (entities.userId !== undefined) {
    await attemptCleanup(failures, 'user disable', async () => {
      const status = await cleanupRequest(page, {
        body: { is_active: false },
        method: 'PATCH',
        path: `/admin/users/${String(entities.userId)}`,
      })
      if (status < 200 || status >= 300) throw new Error('cleanup request failed')
    })
  }
  if (failures.length > 0) throw new Error(`E2E cleanup failed at: ${failures.join(', ')}`)
}

async function expectNoSeriousAxeViolations(page: Page, pageName: string): Promise<void> {
  await page.waitForLoadState('networkidle')
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .every((animation) => animation.playState === 'finished' || animation.playState === 'idle'),
  )
  const results = await new AxeBuilder({ page }).analyze()
  const violations = results.violations.filter(
    (violation) => violation.impact === 'critical' || violation.impact === 'serious',
  )
  expect(violations, `${pageName} has critical or serious accessibility violations`).toEqual([])
}

test('registration, login, and administrator pages have no critical or serious Axe violations', async ({ page }) => {
  await page.goto('login')
  await expect(page.getByRole('heading', { level: 1, name: '账户登录' })).toBeVisible()
  await expectNoSeriousAxeViolations(page, 'login')

  await page.goto('register')
  await expect(page.getByRole('heading', { level: 1, name: '创建账户' })).toBeVisible()
  await expectNoSeriousAxeViolations(page, 'registration')

  await registerFirstAdministrator(page)
  const pages = [
    ['', '控制台概览', '请求与费用趋势'],
    ['providers', '供应商管理', 'create-provider'],
    ['models', '模型管理', 'create-model'],
    ['users', '用户管理', 'create-user'],
    ['api-keys', '接口密钥', 'create-api-key'],
    ['request-logs', '请求日志', 'log-request-id'],
    ['security', '安全设置', 'start-totp'],
  ] as const

  for (const [path, heading, ready] of pages) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
    if (path === '') {
      await expect(page.getByRole('heading', { level: 2, name: ready })).toBeVisible()
    } else {
      await expect(page.getByTestId(ready)).toBeVisible()
      if (['create-provider', 'create-model', 'create-user', 'create-api-key', 'start-totp'].includes(ready)) {
        await expect(page.getByTestId(ready)).toBeEnabled()
      }
    }
    await expectNoSeriousAxeViolations(page, path === '' ? 'dashboard' : path)
  }
})

test('administrator can close and reopen public registration', async ({ page }) => {
  await login(page)
  try {
    await page.goto('security')
    const setting = page.getByTestId('registration-setting')
    await expect(setting).toContainText('已开启')
    await page.getByTestId('registration-toggle').click()
    await expect(setting).toContainText('已关闭')
    await expect(page.getByText('公开注册已关闭')).toBeVisible()

    await page.evaluate(() => {
      window.sessionStorage.clear()
    })
    await page.goto('register')
    await expect(page.getByRole('heading', { level: 1, name: '创建账户' })).toBeVisible()
    await expect(page.getByText('管理员已关闭公开注册')).toBeVisible()
    await expect(page.getByTestId('register-submit')).toHaveCount(0)
    await expect(page.getByRole('link', { name: '返回登录' })).toBeVisible()
  } finally {
    const hasSession = await page.evaluate(
      () => window.sessionStorage.getItem('gateway.access_token') !== null,
    )
    if (!hasSession) await login(page)
    await page.goto('security')
    const setting = page.getByTestId('registration-setting')
    await expect(setting).toBeVisible()
    if ((await setting.textContent())?.includes('已关闭') === true) {
      await page.getByTestId('registration-toggle').click()
      await expect(setting).toContainText('已开启')
    }
  }
})

test('keyboard focus moves from skip link through navigation to the page action', async ({ page }) => {
  await login(page)
  await page.goto('')
  const skipLink = page.getByRole('link', { name: '跳到主要内容' })
  await skipLink.focus()
  await expect(skipLink).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('navigation', { name: '控制台导航' })).toBeFocused()

  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('menuitem', { name: '控制台概览' })).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('menuitem', { name: '供应商管理' })).toBeFocused()
  await page.keyboard.press('Enter')
  const heading = page.getByRole('heading', { level: 1, name: '供应商管理' })
  await expect(heading).toBeFocused()

  await page.keyboard.press('Tab')
  await expect(page.getByTestId('import-catalog')).toBeFocused()
})

test('creates, verifies, and safely cleans up console records', async ({ page }) => {
    const unique = crypto.randomUUID()
    const providerName = `e2e-provider-${unique}`
    const modelCanonicalName = `e2e-model-${unique}`
    const modelDisplayName = `E2E Model ${unique}`
    const modelAlias = `e2e-friendly-model-${unique}`
    const userEmail = `e2e-user-${unique}@example.com`
    const apiKeyName = `e2e-key-${unique}`
    const entities: CreatedEntities = {}
    const entityNames: EntityNames = {
      apiKey: apiKeyName,
      model: modelCanonicalName,
      provider: providerName,
      user: userEmail,
    }

    await login(page)
    for (const metric of [
      '用户总数',
      '活跃接口密钥',
      '启用提供商',
      '启用模型',
      '启用路由',
      '24 小时请求',
      '失败率',
      '24 小时费用',
    ]) {
      await expect(page.getByText(metric).first()).toBeVisible()
    }
    await expect(page.getByRole('heading', { level: 2, name: '请求与费用趋势' })).toBeVisible()

    try {
      await page.goto('providers')
      await page.getByTestId('create-provider').click()
      await page.getByTestId('provider-name').fill(providerName)
      await page.getByTestId('provider-credential').fill(`{"api_key":"placeholder-${unique}"}`)
      await setSwitch(page.getByTestId('provider-enabled'), false)
      await page.getByTestId('protocol-base-url-0').fill('http://127.0.0.1:9/v1')
      await page.getByTestId('provider-submit').click()
      await expect(page.getByTestId('provider-notice')).toContainText('供应商已创建')
      await page.getByTestId('provider-search').fill(providerName)
      const providerCard = page
        .locator('[data-test^="provider-card-"]')
        .filter({ hasText: providerName })
      await expect(providerCard).toContainText('停用')
      entities.providerId = await numericId(
        providerCard.locator('[data-test^="edit-provider-"]'),
        'edit-provider-',
      )

      await page.goto('models')
      await page.getByTestId('create-model').click()
      await page.getByTestId('model-canonical-name').fill(modelCanonicalName)
      await page.getByTestId('model-display-name').fill(modelDisplayName)
      await page.getByTestId('model-input-price').fill('1.25000000')
      await page.getByTestId('model-output-price').fill('2.50000000')
      await page.getByTestId('add-model-alias').click()
      await page.getByTestId('model-alias-0').fill(modelAlias)
      await page.getByTestId('model-submit').click()
      await expect(page.getByTestId('model-notice')).toContainText('模型已创建')
      await page.getByTestId('model-search').fill(modelAlias)
      const modelCard = page
        .locator('[data-test^="model-card-"]')
        .filter({ hasText: modelCanonicalName })
      await expect(modelCard).toContainText(modelAlias)
      entities.modelId = await numericId(
        modelCard.locator('[data-test^="edit-model-"]'),
        'edit-model-',
      )
      await modelCard.locator('[data-test^="create-route-"]').click()
      await page.getByTestId('route-provider').selectOption({ label: providerName })
      await page.getByTestId('route-upstream-model').fill('e2e-original-model')
      await page.getByTestId('route-weight').locator('input').fill('75')
      await page.getByTestId('route-submit').click()
      await expect(page.getByTestId('route-notice')).toContainText('模型路由已创建')
      await modelCard.getByRole('button', { name: /模型路由/ }).click()
      const routeItem = modelCard.locator('.route-item').filter({ hasText: 'e2e-original-model' })
      await expect(routeItem).toContainText('e2e-original-model')
      await expect(routeItem).toContainText('75')
      entities.routeId = await numericId(
        routeItem.locator('[data-test^="delete-route-"]'),
        'delete-route-',
      )

      await page.goto('users')
      await page.getByTestId('create-user').click()
      await page.getByTestId('user-email').fill(userEmail)
      await page.getByTestId('user-password').fill(`e2e-password-${unique}`)
      await page.getByTestId('user-initial-balance').fill('10.00000000')
      await page.getByTestId('user-submit').click()
      await expect(page.getByTestId('user-notice')).toContainText('用户已创建')
      await page.getByTestId('user-search').fill(userEmail)
      const userRow = page.getByRole('row').filter({ hasText: userEmail })
      entities.userId = await numericId(
        userRow.locator('[data-test^="edit-user-"]'),
        'edit-user-',
      )
      await userRow.locator('[data-test^="adjust-user-"]').click()
      await page.getByTestId('balance-amount').fill('+1.25000000')
      await page.getByTestId('balance-reason').fill(`E2E adjustment ${unique}`)
      await page.getByTestId('balance-submit').click()
      await expect(page.getByTestId('user-notice')).toContainText('余额调整成功')
      await expect(userRow).toContainText('11.25000000')

      await page.goto('api-keys')
      await page.getByTestId('create-api-key').click()
      await page.getByTestId('api-key-owner').selectOption({ label: userEmail })
      await page.getByTestId('api-key-name').fill(apiKeyName)
      await page.getByTestId('api-key-scope').selectOption('models')
      await page.getByTestId(`api-key-model-${String(entities.modelId)}`).check()
      await page.getByTestId('api-key-submit').click()
      await expectSafeCondition(
        () => secretIsVisibleAndNonEmpty(page),
        'One-time secret was not visible and non-empty',
      )
      await page.getByTestId('secret-acknowledged').click()
      await page.getByTestId('secret-confirm-close').click()
      await expectSafeCondition(() => secretNodeIsAbsent(page), 'Secret node was not removed')
      await expectSafeCondition(() => localStorageIsEmpty(page), 'Local storage was not empty')
      await expectSafeCondition(
        () => sessionStorageHasOnlyTokens(page),
        'Session storage keys were not the exact allowlist',
      )
      await page.getByTestId('api-key-search').fill(apiKeyName)
      const apiKeyRow = page.getByRole('row').filter({ hasText: apiKeyName })
      entities.apiKeyId = await numericId(
        apiKeyRow.locator('[data-test^="delete-api-key-"]'),
        'delete-api-key-',
      )
      await expect(apiKeyRow).toContainText('指定模型')

      await page.goto('request-logs')
      const requestId = crypto.randomUUID()
      await page.getByTestId('log-request-id').fill(requestId)
      await page.getByTestId('log-status').selectOption('completed')
      await page.getByTestId('log-protocol').selectOption('openai')
      await page.getByTestId('log-page-size').selectOption('50')
      const requestPromise = page.waitForRequest((request) => {
        const url = new URL(request.url())
        return url.pathname === '/admin/request-logs' && url.searchParams.get('request_id') === requestId
      })
      await page.getByRole('button', { name: '查询' }).click()
      const filterRequest = await requestPromise
      const filterUrl = new URL(filterRequest.url())
      expect(filterUrl.searchParams.get('status')).toBe('completed')
      expect(filterUrl.searchParams.get('protocol')).toBe('openai')
      expect(filterUrl.searchParams.get('page_size')).toBe('50')
      await expect(page.getByText('第 1 页').first()).toBeVisible()
      await expect(page.getByText('暂无匹配的请求日志')).toBeVisible()
    } finally {
      await cleanup(page, entities, entityNames)
    }
})
