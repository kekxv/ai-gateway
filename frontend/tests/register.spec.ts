import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type { CurrentUser } from '@/api/types'
import RegisterView from '@/views/RegisterView.vue'

const adminUser: CurrentUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin',
  is_active: true,
  totp_enabled: false,
  created_at: '2026-07-28T00:00:00',
  updated_at: '2026-07-28T00:00:00',
}

const regularUser: CurrentUser = {
  ...adminUser,
  id: 2,
  email: 'member@example.com',
  role: 'user',
}

const server = setupServer()

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

afterEach(() => {
  server.resetHandlers()
  document.body.innerHTML = ''
})

afterAll(() => {
  server.close()
})

beforeEach(() => {
  sessionStorage.clear()
  setActivePinia(createPinia())
})

async function mountRegistration() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/register', name: 'register', component: RegisterView },
      { path: '/login', name: 'login', component: { template: '<main>登录</main>' } },
      { path: '/', name: 'dashboard', component: { template: '<main>控制台</main>' } },
      { path: '/security', name: 'security', component: { template: '<main>安全设置</main>' } },
    ],
  })
  await router.push('/register')
  await router.isReady()
  const wrapper = mount(RegisterView, {
    attachTo: document.body,
    global: { plugins: [router] },
  })
  return { router, wrapper }
}

async function fillRegistration(
  wrapper: Awaited<ReturnType<typeof mountRegistration>>['wrapper'],
): Promise<void> {
  await wrapper.get('[data-test="register-email"]').setValue(' New.User@Example.com ')
  await wrapper.get('[data-test="register-password"]').setValue('registration-password')
  await wrapper
    .get('[data-test="register-password-confirm"]')
    .setValue('registration-password')
}

describe('注册页面', () => {
  it.each([
    ['admin', adminUser, 'dashboard'],
    ['user', regularUser, 'security'],
  ] as const)('仅提交邮箱和密码，并按 %s 角色进入正确页面', async (_, user, destination) => {
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
      http.get('/auth/me', () => HttpResponse.json(user)),
    )
    const { router, wrapper } = await mountRegistration()
    await fillRegistration(wrapper)

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(requests).toEqual([
      { email: 'New.User@Example.com', password: 'registration-password' },
    ])
    expect(router.currentRoute.value.name).toBe(destination)
    expect((wrapper.vm as unknown as { password: string }).password).toBe('')
    expect((wrapper.vm as unknown as { passwordConfirmation: string }).passwordConfirmation).toBe(
      '',
    )
    wrapper.unmount()
  })

  it('本地拒绝不一致的密码，并立即清空两个密码字段', async () => {
    const request = vi.fn()
    server.use(
      http.post('/auth/register', () => {
        request()
        return HttpResponse.json({})
      }),
    )
    const { wrapper } = await mountRegistration()
    await wrapper.get('[data-test="register-email"]').setValue('member@example.com')
    await wrapper.get('[data-test="register-password"]').setValue('registration-password')
    await wrapper.get('[data-test="register-password-confirm"]').setValue('different-password')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(request).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('两次输入的密码不一致')
    expect((wrapper.vm as unknown as { password: string }).password).toBe('')
    expect((wrapper.vm as unknown as { passwordConfirmation: string }).passwordConfirmation).toBe(
      '',
    )
    wrapper.unmount()
  })

  it('注册失败后显示安全提示并清空密码', async () => {
    server.use(
      http.post('/auth/register', () =>
        HttpResponse.json(
          { detail: { code: 'email_exists', message: 'unsafe upstream detail' } },
          { status: 409 },
        ),
      ),
    )
    const { wrapper } = await mountRegistration()
    await fillRegistration(wrapper)

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('邮箱已被注册')
    expect(wrapper.text()).not.toContain('unsafe upstream detail')
    expect((wrapper.vm as unknown as { password: string }).password).toBe('')
    expect((wrapper.vm as unknown as { passwordConfirmation: string }).passwordConfirmation).toBe(
      '',
    )
    wrapper.unmount()
  })

  it('请求期间阻止重复提交', async () => {
    let release!: () => void
    let calls = 0
    server.use(
      http.post('/auth/register', async () => {
        calls += 1
        await new Promise<void>((resolve) => {
          release = resolve
        })
        return HttpResponse.json(
          { access_token: 'access', refresh_token: 'refresh', token_type: 'bearer' },
          { status: 201 },
        )
      }),
      http.get('/auth/me', () => HttpResponse.json(adminUser)),
    )
    const { wrapper } = await mountRegistration()
    await fillRegistration(wrapper)

    await wrapper.get('form').trigger('submit')
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => {
      expect(calls).toBe(1)
    })
    expect(wrapper.get('[data-test="register-submit"]').attributes('disabled')).toBeDefined()
    release()
    await flushPromises()
    wrapper.unmount()
  })

  it('卸载时清空尚未提交的密码', async () => {
    const { wrapper } = await mountRegistration()
    await wrapper.get('[data-test="register-password"]').setValue('registration-password')
    await wrapper
      .get('[data-test="register-password-confirm"]')
      .setValue('registration-password')
    const vm = wrapper.vm as unknown as {
      password: string
      passwordConfirmation: string
    }

    wrapper.unmount()

    expect(vm.password).toBe('')
    expect(vm.passwordConfirmation).toBe('')
  })

  it('说明首位用户策略并提供登录链接', async () => {
    const { wrapper } = await mountRegistration()

    expect(wrapper.text()).toContain('第一个注册的账户将自动成为管理员')
    expect(wrapper.get('a[href="/login"]').text()).toContain('登录')
    wrapper.unmount()
  })
})
