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

  it('rejects a non-admin login and clears its tokens', async () => {
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

    await expect(store.login({ email: regularUser.email, password: 'secret' })).rejects.toEqual(
      expect.objectContaining({
        status: 403,
        code: 'admin_required',
        message: '仅管理员可以访问管理控制台',
      }),
    )
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

    await expect(request).rejects.toBeInstanceOf(ApiError)
    await expect(request).rejects.not.toHaveProperty('message', expect.stringContaining('do-not-repeat-this'))
  })
})
