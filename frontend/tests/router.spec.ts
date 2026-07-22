import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createAppRouter, resolveLoginRedirect } from '@/router'
import { useAuthStore } from '@/stores/auth'
import NotFoundView from '@/views/NotFoundView.vue'

const adminUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin' as const,
  is_active: true,
  totp_enabled: false,
  created_at: '2026-07-22T00:00:00',
  updated_at: '2026-07-22T00:00:00',
}

describe('导航守卫', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('将未登录的控制台路由重定向到登录页并保留目标地址', async () => {
    const router = createAppRouter(createMemoryHistory())

    await router.push('/providers?enabled=true#details')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/providers?enabled=true#details')
  })

  it('将未登录的未知路由重定向到登录页并保留完整地址', async () => {
    const router = createAppRouter(createMemoryHistory())

    await router.push('/unknown/path?source=test#missing')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/unknown/path?source=test#missing')
  })

  it('允许已登录管理员查看未知路由的 404 页面', async () => {
    const auth = useAuthStore()
    vi.spyOn(auth, 'restore').mockImplementation(() => {
      auth.user = adminUser
      auth.ready = true
      return Promise.resolve()
    })
    const router = createAppRouter(createMemoryHistory())

    await router.push('/unknown/path')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('not-found')
  })

  it('等待异步会话恢复后再允许访问受保护页面，并且只恢复一次', async () => {
    const auth = useAuthStore()
    const restore = vi.spyOn(auth, 'restore').mockImplementation(async () => {
      await Promise.resolve()
      auth.user = adminUser
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
      auth.user = adminUser
      auth.ready = true
      return Promise.resolve()
    })
    const router = createAppRouter(createMemoryHistory())

    await router.push('/login')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('dashboard')
  })

  it('保留安全的站内登录后目标地址', () => {
    expect(resolveLoginRedirect('/providers?enabled=true#details')).toBe(
      '/providers?enabled=true#details',
    )
  })

  it.each([
    '//evil.example/path',
    '///evil.example/path',
    '/\\evil.example/path',
    '/%5C%5Cevil.example/path',
    '/%2F%2Fevil.example/path',
    'https://evil.example/path',
    'providers',
  ])('拒绝恶意登录后目标地址 %s', (redirect) => {
    expect(resolveLoginRedirect(redirect)).toBe('/')
  })

  it('404 页面使用单一语义链接返回控制台', () => {
    const wrapper = mount(NotFoundView, {
      global: {
        stubs: {
          RouterLink: {
            props: ['to'],
            template: '<a class="router-link" :href="to"><slot /></a>',
          },
        },
      },
    })

    expect(wrapper.get('a.not-found__link').text()).toBe('返回控制台')
    expect(wrapper.find('button').exists()).toBe(false)
    wrapper.unmount()
  })
})
