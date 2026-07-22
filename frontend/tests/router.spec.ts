import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createAppRouter } from '@/router'
import { useAuthStore } from '@/stores/auth'

describe('导航守卫', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('将未登录的控制台路由重定向到登录页并保留目标地址', async () => {
    const router = createAppRouter(createMemoryHistory())

    await router.push('/providers')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/providers')
  })

  it('等待异步会话恢复后再允许访问受保护页面，并且只恢复一次', async () => {
    const auth = useAuthStore()
    const restore = vi.spyOn(auth, 'restore').mockImplementation(async () => {
      await Promise.resolve()
      auth.user = {
        id: 1,
        email: 'admin@example.com',
        role: 'admin',
        is_active: true,
        totp_enabled: false,
        created_at: '2026-07-22T00:00:00',
        updated_at: '2026-07-22T00:00:00',
      }
      auth.ready = true
    })
    const router = createAppRouter(createMemoryHistory())

    await router.push('/models')
    await router.push('/users')

    expect(router.currentRoute.value.name).toBe('users')
    expect(restore).toHaveBeenCalledTimes(1)
  })

  it('将已登录用户从登录页重定向到控制台首页', async () => {
    const auth = useAuthStore()
    vi.spyOn(auth, 'restore').mockImplementation(() => {
      auth.user = {
        id: 1,
        email: 'admin@example.com',
        role: 'admin',
        is_active: true,
        totp_enabled: false,
        created_at: '2026-07-22T00:00:00',
        updated_at: '2026-07-22T00:00:00',
      }
      auth.ready = true
      return Promise.resolve()
    })
    const router = createAppRouter(createMemoryHistory())

    await router.push('/login')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('dashboard')
  })
})
