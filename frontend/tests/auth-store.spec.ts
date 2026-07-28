import { createPinia, setActivePinia } from 'pinia'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { apiClient, ApiError } from '@/api/client'
import type { CurrentUser } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

const adminUser: CurrentUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin',
  is_active: true,
  totp_enabled: false,
  created_at: '2026-07-22T00:00:00',
  updated_at: '2026-07-22T00:00:00',
}

const regularUser: CurrentUser = {
  ...adminUser,
  id: 2,
  email: 'user@example.com',
  role: 'user',
}

const replacementAdmin: CurrentUser = {
  ...adminUser,
  id: 3,
  email: 'replacement-admin@example.com',
}

function createDeferred(): { promise: Promise<void>; resolve: () => void } {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, resolve: release }
}

const server = setupServer()

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

afterEach(() => {
  server.resetHandlers()
})

afterAll(() => {
  server.close()
})

beforeEach(() => {
  sessionStorage.clear()
  setActivePinia(createPinia())
})

describe('authentication store', () => {
  it('restores a valid admin session', async () => {
    sessionStorage.setItem('gateway.access_token', 'access')
    sessionStorage.setItem('gateway.refresh_token', 'refresh')
    server.use(http.get('/auth/me', () => HttpResponse.json(adminUser)))

    const store = useAuthStore()
    await store.restore()

    expect(store.user).toEqual(adminUser)
    expect(store.isAdmin).toBe(true)
    expect(store.authenticated).toBe(true)
    expect(store.ready).toBe(true)
  })

  it('restores a valid regular-user session', async () => {
    sessionStorage.setItem('gateway.access_token', 'access')
    sessionStorage.setItem('gateway.refresh_token', 'refresh')
    server.use(http.get('/auth/me', () => HttpResponse.json(regularUser)))

    const store = useAuthStore()
    await store.restore()

    expect(store.user).toEqual(regularUser)
    expect(store.isAdmin).toBe(false)
    expect(store.authenticated).toBe(true)
  })

  it('clears storage when refresh fails', async () => {
    sessionStorage.setItem('gateway.access_token', 'expired')
    sessionStorage.setItem('gateway.refresh_token', 'refresh')
    server.use(
      http.get('/auth/me', () => new HttpResponse(null, { status: 401 })),
      http.post('/auth/refresh', () => new HttpResponse(null, { status: 401 })),
    )

    await expect(useAuthStore().restore()).resolves.toBeUndefined()

    expect(sessionStorage.length).toBe(0)
    expect(useAuthStore().ready).toBe(true)
  })

  it('logs in only after the token response succeeds', async () => {
    server.use(
      http.post('/auth/login', () =>
        HttpResponse.json({
          access_token: 'access',
          refresh_token: 'refresh',
          token_type: 'bearer',
        }),
      ),
      http.get('/auth/me', () => HttpResponse.json(adminUser)),
    )

    const store = useAuthStore()
    await store.login({ email: adminUser.email, password: 'secret' })

    expect(store.user).toEqual(adminUser)
    expect(sessionStorage.getItem('gateway.access_token')).toBe('access')
    expect(sessionStorage.getItem('gateway.refresh_token')).toBe('refresh')
  })

  it('does not let a login response restore the session after logout', async () => {
    const loginStarted = createDeferred()
    const releaseLogin = createDeferred()
    server.use(
      http.post('/auth/login', async () => {
        loginStarted.resolve()
        await releaseLogin.promise
        return HttpResponse.json({
          access_token: 'stale-access',
          refresh_token: 'stale-refresh',
          token_type: 'bearer',
        })
      }),
      http.get('/auth/me', () => HttpResponse.json(adminUser)),
    )
    const store = useAuthStore()

    const outcome = store
      .login({ email: adminUser.email, password: 'secret' })
      .catch((error: unknown) => error)
    await loginStarted.promise
    store.logout()
    releaseLogin.resolve()

    expect(await outcome).toEqual(expect.objectContaining({ code: 'session_changed' }))
    expect(sessionStorage.length).toBe(0)
    expect(store.user).toBeNull()
    expect(store.ready).toBe(true)
  })

  it('does not let an older successful login overwrite a newer login', async () => {
    const oldUserStarted = createDeferred()
    const releaseOldUser = createDeferred()
    server.use(
      http.post('/auth/login', async ({ request }) => {
        const body = (await request.json()) as { email: string }
        const prefix = body.email === adminUser.email ? 'old' : 'new'
        return HttpResponse.json({
          access_token: `${prefix}-access`,
          refresh_token: `${prefix}-refresh`,
          token_type: 'bearer',
        })
      }),
      http.get('/auth/me', async ({ request }) => {
        if (request.headers.get('Authorization') === 'Bearer old-access') {
          oldUserStarted.resolve()
          await releaseOldUser.promise
          return HttpResponse.json(adminUser)
        }
        return HttpResponse.json(replacementAdmin)
      }),
    )
    const store = useAuthStore()

    const oldOutcome = store
      .login({ email: adminUser.email, password: 'old-secret' })
      .catch((error: unknown) => error)
    await oldUserStarted.promise
    await store.login({ email: replacementAdmin.email, password: 'new-secret' })
    releaseOldUser.resolve()

    expect(await oldOutcome).toEqual(expect.objectContaining({ code: 'session_changed' }))
    expect(sessionStorage.getItem('gateway.access_token')).toBe('new-access')
    expect(sessionStorage.getItem('gateway.refresh_token')).toBe('new-refresh')
    expect(store.user).toEqual(replacementAdmin)
    expect(store.ready).toBe(true)
  })

  it('does not let an older failed login clear a newer login', async () => {
    const oldLoginStarted = createDeferred()
    const releaseOldLogin = createDeferred()
    server.use(
      http.post('/auth/login', async ({ request }) => {
        const body = (await request.json()) as { email: string }
        if (body.email === adminUser.email) {
          oldLoginStarted.resolve()
          await releaseOldLogin.promise
          return HttpResponse.json(
            { detail: { code: 'invalid_credentials', message: 'Invalid credentials' } },
            { status: 401 },
          )
        }
        return HttpResponse.json({
          access_token: 'new-access',
          refresh_token: 'new-refresh',
          token_type: 'bearer',
        })
      }),
      http.get('/auth/me', () => HttpResponse.json(replacementAdmin)),
    )
    const store = useAuthStore()

    const oldOutcome = store
      .login({ email: adminUser.email, password: 'wrong-secret' })
      .catch((error: unknown) => error)
    await oldLoginStarted.promise
    await store.login({ email: replacementAdmin.email, password: 'new-secret' })
    releaseOldLogin.resolve()

    expect(await oldOutcome).toEqual(expect.objectContaining({ code: 'session_changed' }))
    expect(sessionStorage.getItem('gateway.access_token')).toBe('new-access')
    expect(sessionStorage.getItem('gateway.refresh_token')).toBe('new-refresh')
    expect(store.user).toEqual(replacementAdmin)
    expect(store.ready).toBe(true)
  })

  it('does not let restore complete after logout', async () => {
    sessionStorage.setItem('gateway.access_token', 'old-access')
    sessionStorage.setItem('gateway.refresh_token', 'old-refresh')
    const restoreStarted = createDeferred()
    const releaseRestore = createDeferred()
    server.use(
      http.get('/auth/me', async () => {
        restoreStarted.resolve()
        await releaseRestore.promise
        return HttpResponse.json(adminUser)
      }),
    )
    const store = useAuthStore()

    const outcome = store.restore().catch((error: unknown) => error)
    await restoreStarted.promise
    store.logout()
    releaseRestore.resolve()

    expect(await outcome).toEqual(expect.objectContaining({ code: 'session_changed' }))
    expect(sessionStorage.length).toBe(0)
    expect(store.user).toBeNull()
    expect(store.ready).toBe(true)
  })

  it('stores no tokens when login fails and uses a Chinese safe message', async () => {
    server.use(
      http.post('/auth/login', () =>
        HttpResponse.json(
          {
            detail: {
              code: 'invalid_credentials',
              message: 'Invalid email or password',
              request_id: 'request-1',
            },
          },
          { status: 401 },
        ),
      ),
    )

    const request = useAuthStore().login({ email: adminUser.email, password: 'wrong-secret' })

    await expect(request).rejects.toEqual(
      expect.objectContaining({
        status: 401,
        code: 'invalid_credentials',
        message: '邮箱或密码错误',
        requestId: 'request-1',
      }),
    )
    expect(sessionStorage.length).toBe(0)
    expect(useAuthStore().user).toBeNull()
  })

  it('accepts a regular-user login and reports the role', async () => {
    server.use(
      http.post('/auth/login', () =>
        HttpResponse.json({
          access_token: 'access',
          refresh_token: 'refresh',
          token_type: 'bearer',
        }),
      ),
      http.get('/auth/me', () => HttpResponse.json(regularUser)),
    )

    const store = useAuthStore()

    await store.login({ email: regularUser.email, password: 'secret' })

    expect(sessionStorage.getItem('gateway.access_token')).toBe('access')
    expect(sessionStorage.getItem('gateway.refresh_token')).toBe('refresh')
    expect(store.user).toEqual(regularUser)
    expect(store.isAdmin).toBe(false)
  })

  it('registers, stores the returned tokens, and loads the new user', async () => {
    const requests: unknown[] = []
    server.use(
      http.post('/auth/register', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json(
          {
            access_token: 'registered-access',
            refresh_token: 'registered-refresh',
            token_type: 'bearer',
          },
          { status: 201 },
        )
      }),
      http.get('/auth/me', () => HttpResponse.json(regularUser)),
    )

    const store = useAuthStore()
    await store.register({ email: regularUser.email, password: 'registration-password' })

    expect(requests).toEqual([
      { email: regularUser.email, password: 'registration-password' },
    ])
    expect(sessionStorage.getItem('gateway.access_token')).toBe('registered-access')
    expect(sessionStorage.getItem('gateway.refresh_token')).toBe('registered-refresh')
    expect(store.user).toEqual(regularUser)
  })

  it('does not let a registration response restore the session after logout', async () => {
    const registrationStarted = createDeferred()
    const releaseRegistration = createDeferred()
    server.use(
      http.post('/auth/register', async () => {
        registrationStarted.resolve()
        await releaseRegistration.promise
        return HttpResponse.json(
          {
            access_token: 'stale-access',
            refresh_token: 'stale-refresh',
            token_type: 'bearer',
          },
          { status: 201 },
        )
      }),
      http.get('/auth/me', () => HttpResponse.json(regularUser)),
    )
    const store = useAuthStore()

    const outcome = store
      .register({ email: regularUser.email, password: 'registration-password' })
      .catch((error: unknown) => error)
    await registrationStarted.promise
    store.logout()
    releaseRegistration.resolve()

    expect(await outcome).toEqual(expect.objectContaining({ code: 'session_changed' }))
    expect(sessionStorage.length).toBe(0)
    expect(store.user).toBeNull()
  })

  it('serializes concurrent access-token refreshes', async () => {
    sessionStorage.setItem('gateway.access_token', 'expired')
    sessionStorage.setItem('gateway.refresh_token', 'refresh')
    let refreshCalls = 0
    server.use(
      http.get('/admin/first', ({ request }) => {
        if (request.headers.get('Authorization') === 'Bearer renewed') {
          return HttpResponse.json({ ok: true })
        }
        return new HttpResponse(null, { status: 401 })
      }),
      http.get('/admin/second', ({ request }) => {
        if (request.headers.get('Authorization') === 'Bearer renewed') {
          return HttpResponse.json({ ok: true })
        }
        return new HttpResponse(null, { status: 401 })
      }),
      http.post('/auth/refresh', async () => {
        refreshCalls += 1
        await Promise.resolve()
        return HttpResponse.json({ access_token: 'renewed', token_type: 'bearer' })
      }),
    )

    await Promise.all([apiClient.get('/admin/first'), apiClient.get('/admin/second')])

    expect(refreshCalls).toBe(1)
    expect(sessionStorage.getItem('gateway.access_token')).toBe('renewed')
  })

  it('does not restore stale tokens when logout happens during refresh', async () => {
    sessionStorage.setItem('gateway.access_token', 'old-access')
    sessionStorage.setItem('gateway.refresh_token', 'old-refresh')
    server.use(http.get('/auth/me', () => HttpResponse.json(adminUser)))
    const store = useAuthStore()
    await store.restore()

    const refreshStarted = createDeferred()
    const releaseRefresh = createDeferred()
    server.use(
      http.get('/admin/race', ({ request }) => {
        if (request.headers.get('Authorization') === 'Bearer stale-access') {
          return HttpResponse.json({ ok: true })
        }
        return new HttpResponse(null, { status: 401 })
      }),
      http.post('/auth/refresh', async () => {
        refreshStarted.resolve()
        await releaseRefresh.promise
        return HttpResponse.json({ access_token: 'stale-access', token_type: 'bearer' })
      }),
    )

    const pendingRequest = apiClient.get('/admin/race')
    await refreshStarted.promise
    store.logout()
    releaseRefresh.resolve()

    await expect(pendingRequest).rejects.toEqual(
      expect.objectContaining({ code: 'session_changed' }),
    )
    expect(sessionStorage.length).toBe(0)
    expect(store.user).toBeNull()
  })

  it('does not let an old refresh overwrite a newly logged-in session', async () => {
    sessionStorage.setItem('gateway.access_token', 'old-access')
    sessionStorage.setItem('gateway.refresh_token', 'old-refresh')
    server.use(http.get('/auth/me', () => HttpResponse.json(adminUser)))
    const store = useAuthStore()
    await store.restore()

    const refreshStarted = createDeferred()
    const releaseRefresh = createDeferred()
    const newRefreshStarted = createDeferred()
    const releaseNewRefresh = createDeferred()
    const secondNewSessionUnauthorized = createDeferred()
    let oldRefreshCalls = 0
    let newRefreshCalls = 0
    let newSessionUnauthorizedCalls = 0
    server.use(
      http.get('/admin/race', ({ request }) => {
        if (request.headers.get('Authorization') === 'Bearer stale-access') {
          return HttpResponse.json({ ok: true })
        }
        return new HttpResponse(null, { status: 401 })
      }),
      http.get('/admin/new-session', ({ request }) => {
        if (request.headers.get('Authorization') === 'Bearer renewed-new-access') {
          return HttpResponse.json({ ok: true })
        }
        newSessionUnauthorizedCalls += 1
        if (newSessionUnauthorizedCalls === 2) secondNewSessionUnauthorized.resolve()
        return new HttpResponse(null, { status: 401 })
      }),
      http.post('/auth/refresh', async ({ request }) => {
        const payload = (await request.json()) as { refresh_token?: unknown }
        if (payload.refresh_token === 'old-refresh') {
          oldRefreshCalls += 1
          refreshStarted.resolve()
          await releaseRefresh.promise
          return HttpResponse.json({ access_token: 'stale-access', token_type: 'bearer' })
        }
        newRefreshCalls += 1
        newRefreshStarted.resolve()
        await releaseNewRefresh.promise
        return HttpResponse.json({ access_token: 'renewed-new-access', token_type: 'bearer' })
      }),
      http.post('/auth/login', () =>
        HttpResponse.json({
          access_token: 'new-access',
          refresh_token: 'new-refresh',
          token_type: 'bearer',
        }),
      ),
      http.get('/auth/me', ({ request }) => {
        if (request.headers.get('Authorization') === 'Bearer new-access') {
          return HttpResponse.json(replacementAdmin)
        }
        return HttpResponse.json(adminUser)
      }),
    )

    const pendingRequest = apiClient.get('/admin/race')
    await refreshStarted.promise
    await store.login({ email: replacementAdmin.email, password: 'new-secret' })
    const firstNewSessionRequest = apiClient.get('/admin/new-session')
    await newRefreshStarted.promise
    releaseRefresh.resolve()

    await expect(pendingRequest).rejects.toEqual(
      expect.objectContaining({ code: 'session_changed' }),
    )
    const secondNewSessionRequest = apiClient.get('/admin/new-session')
    await secondNewSessionUnauthorized.promise
    await new Promise<void>((resolve) => {
      setTimeout(resolve, 0)
    })
    releaseNewRefresh.resolve()
    await Promise.all([firstNewSessionRequest, secondNewSessionRequest])

    expect(oldRefreshCalls).toBe(1)
    expect(newRefreshCalls).toBe(1)
    expect(sessionStorage.getItem('gateway.access_token')).toBe('renewed-new-access')
    expect(sessionStorage.getItem('gateway.refresh_token')).toBe('new-refresh')
    expect(store.user).toEqual(replacementAdmin)
  })

  it('clears an established Pinia session when background refresh fails', async () => {
    sessionStorage.setItem('gateway.access_token', 'access')
    sessionStorage.setItem('gateway.refresh_token', 'refresh')
    server.use(http.get('/auth/me', () => HttpResponse.json(adminUser)))
    const store = useAuthStore()
    await store.restore()

    server.use(
      http.get('/admin/background', () => new HttpResponse(null, { status: 401 })),
      http.post('/auth/refresh', () => new HttpResponse(null, { status: 401 })),
    )

    await expect(apiClient.get('/admin/background')).rejects.toBeInstanceOf(ApiError)

    expect(sessionStorage.length).toBe(0)
    expect(store.user).toBeNull()
    expect(store.authenticated).toBe(false)
  })

  it('normalizes validation errors without exposing submitted secrets', async () => {
    server.use(
      http.post('/auth/login', () =>
        HttpResponse.json(
          {
            detail: [{ loc: ['body', 'password'], msg: 'Field required', type: 'missing' }],
          },
          { status: 422 },
        ),
      ),
    )

    const request = useAuthStore().login({
      email: adminUser.email,
      password: 'do-not-repeat-this',
    })

    await expect(request).rejects.toEqual(
      expect.objectContaining({
        status: 422,
        code: 'validation_error',
        message: '密码参数无效',
      }),
    )
    await expect(request).rejects.not.toHaveProperty(
      'message',
      expect.stringContaining('do-not-repeat-this'),
    )
    await expect(request).rejects.not.toHaveProperty(
      'message',
      expect.stringContaining('Field required'),
    )
  })
})
