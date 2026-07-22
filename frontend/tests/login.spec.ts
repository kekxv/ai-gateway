import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createMemoryHistory } from 'vue-router'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type { CurrentUser } from '@/api/types'
import App from '@/App.vue'
import LoginView from '@/views/LoginView.vue'
import { createAppRouter } from '@/router'
import { useAuthStore } from '@/stores/auth'

const adminUser: CurrentUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin',
  is_active: true,
  totp_enabled: true,
  created_at: '2026-07-22T00:00:00',
  updated_at: '2026-07-22T00:00:00',
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
  setActivePinia(createPinia())
})

async function mountLogin(redirect?: string) {
  const router = createAppRouter(createMemoryHistory())
  await router.push({ name: 'login', query: redirect === undefined ? {} : { redirect } })
  await router.isReady()
  const wrapper = mount(LoginView, {
    attachTo: document.body,
    global: {
      plugins: [router],
    },
  })
  return { router, wrapper }
}

describe('登录页面', () => {
  it('仅在服务端要求双重验证后显示验证码输入框', async () => {
    const requests: unknown[] = []
    const totpFocusDisabledStates: boolean[] = []
    vi.spyOn(HTMLInputElement.prototype, 'focus').mockImplementation(function (
      this: HTMLInputElement,
    ) {
      if (this.name === 'totp_code') totpFocusDisabledStates.push(this.disabled)
      HTMLElement.prototype.focus.call(this)
    })
    server.use(
      http.post('/auth/login', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json(
          { detail: { code: 'totp_required', message: 'TOTP code is required' } },
          { status: 401 },
        )
      }),
    )
    const { wrapper } = await mountLogin()

    expect(wrapper.find('[data-test="totp-code"]').exists()).toBe(false)
    await wrapper.get('[data-test="email"]').setValue('admin@example.com')
    await wrapper.get('[data-test="password"]').setValue('secret-pass')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(requests).toEqual([{ email: 'admin@example.com', password: 'secret-pass' }])
    expect(wrapper.find('[data-test="totp-code"]').exists()).toBe(true)
    expect(totpFocusDisabledStates).toEqual([false])
    expect(document.activeElement).toBe(wrapper.get('[data-test="totp-code"]').element)
    expect((wrapper.get('[data-test="password"]').element as HTMLInputElement).value).toBe(
      'secret-pass',
    )
  })

  it('第二阶段提交全部凭据，成功后清空敏感字段并返回目标页面', async () => {
    const requests: unknown[] = []
    server.use(
      http.post('/auth/login', async ({ request }) => {
        const body = await request.json()
        requests.push(body)
        if (requests.length === 1) {
          return HttpResponse.json(
            { detail: { code: 'totp_required', message: 'TOTP code is required' } },
            { status: 401 },
          )
        }
        return HttpResponse.json({
          access_token: 'access',
          refresh_token: 'refresh',
          token_type: 'bearer',
        })
      }),
      http.get('/auth/me', () => HttpResponse.json(adminUser)),
    )
    const { router, wrapper } = await mountLogin('/providers')

    await wrapper.get('[data-test="email"]').setValue('admin@example.com')
    await wrapper.get('[data-test="password"]').setValue('secret-pass')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-test="totp-code"]').setValue('123456')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('providers')
    })

    expect(requests).toEqual([
      { email: 'admin@example.com', password: 'secret-pass' },
      { email: 'admin@example.com', password: 'secret-pass', totp_code: '123456' },
    ])
    expect(wrapper.find('.login-alert').exists()).toBe(false)
    expect((wrapper.get('[data-test="password"]').element as HTMLInputElement).value).toBe('')
  })

  it('请求进行期间禁用提交按钮，失败后清空密码', async () => {
    let releaseRequest!: () => void
    server.use(
      http.post('/auth/login', async () => {
        await new Promise<void>((resolve) => {
          releaseRequest = resolve
        })
        return HttpResponse.json(
          { detail: { code: 'invalid_credentials', message: 'Invalid credentials' } },
          { status: 401 },
        )
      }),
    )
    const { router, wrapper } = await mountLogin()
    await wrapper.get('[data-test="email"]').setValue('admin@example.com')
    await wrapper.get('[data-test="password"]').setValue('secret-pass')

    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => {
      expect(wrapper.get('[data-test="submit"]').attributes('disabled')).toBeDefined()
    })
    releaseRequest()
    await flushPromises()
    await router.push('/missing')
    await flushPromises()

    expect((wrapper.get('[data-test="password"]').element as HTMLInputElement).value).toBe('')
  })

  it('通过 RouterView 离开登录页时清空已填写的密码和验证码', async () => {
    server.use(
      http.post('/auth/login', () =>
        HttpResponse.json(
          { detail: { code: 'totp_required', message: 'TOTP code is required' } },
          { status: 401 },
        ),
      ),
    )
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createAppRouter(createMemoryHistory())
    await router.push({ name: 'login' })
    await router.isReady()
    const app = mount(App, {
      attachTo: document.body,
      global: { plugins: [pinia, router] },
    })

    const login = app.getComponent(LoginView)
    await login.get('[data-test="email"]').setValue('admin@example.com')
    await login.get('[data-test="password"]').setValue('secret-pass')
    await login.get('form').trigger('submit')
    await flushPromises()
    await login.get('[data-test="totp-code"]').setValue('123456')
    expect((login.vm as unknown as { password: string }).password).toBe('secret-pass')
    expect((login.vm as unknown as { totpCode: string }).totpCode).toBe('123456')

    useAuthStore().user = adminUser
    await router.push('/providers')
    await flushPromises()

    expect(app.findComponent(LoginView).exists()).toBe(false)
    expect((login.vm as unknown as { password: string }).password).toBe('')
    expect((login.vm as unknown as { totpCode: string }).totpCode).toBe('')
  })
})
