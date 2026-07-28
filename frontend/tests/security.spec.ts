import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import QrcodeVue from 'qrcode.vue'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type { CurrentUser } from '@/api/types'
import { routes } from '@/router'
import { useAuthStore } from '@/stores/auth'
import SecurityView from '@/views/SecurityView.vue'

interface Deferred {
  promise: Promise<void>
  resolve: () => void
}

function deferred(): Deferred {
  let resolve!: () => void
  const promise = new Promise<void>((resolver) => {
    resolve = resolver
  })
  return { promise, resolve }
}

const disabledAdmin: CurrentUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin',
  is_active: true,
  totp_enabled: false,
  created_at: '2026-07-22T00:00:00Z',
  updated_at: '2026-07-22T00:00:00Z',
}

const enabledAdmin: CurrentUser = {
  ...disabledAdmin,
  totp_enabled: true,
  updated_at: '2026-07-22T01:00:00Z',
}

const regularUser: CurrentUser = {
  ...disabledAdmin,
  id: 2,
  email: 'member@example.com',
  role: 'user',
}

const server = setupServer()

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

beforeEach(() => {
  server.use(
    http.get('/admin/settings/registration', () => HttpResponse.json({ enabled: true })),
  )
})

afterEach(() => {
  vi.restoreAllMocks()
  server.resetHandlers()
  document.body.innerHTML = ''
})

afterAll(() => {
  server.close()
})

function mountSecurity(user: CurrentUser = disabledAdmin) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = user
  const wrapper = mount(SecurityView, {
    attachTo: document.body,
    global: { plugins: [pinia] },
  })
  return { auth, wrapper }
}

function apiError(code: string, status = 400) {
  return HttpResponse.json(
    { detail: { code, message: 'The server message must not be displayed' } },
    { status },
  )
}

describe('TOTP 安全设置', () => {
  it('管理员可以在安全页关闭和重新开启公开注册', async () => {
    const updates: unknown[] = []
    server.use(
      http.patch('/admin/settings/registration', async ({ request }) => {
        const body = await request.json()
        updates.push(body)
        return HttpResponse.json(body)
      }),
    )
    const { wrapper } = mountSecurity()
    await flushPromises()

    expect(wrapper.get('[data-test="registration-setting"]').text()).toContain('已开启')
    await wrapper.get('[data-test="registration-toggle"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="registration-setting"]').text()).toContain('已关闭')

    await wrapper.get('[data-test="registration-toggle"]').trigger('click')
    await flushPromises()

    expect(updates).toEqual([{ enabled: false }, { enabled: true }])
    expect(wrapper.get('[data-test="registration-setting"]').text()).toContain('已开启')
    wrapper.unmount()
  })

  it('普通用户看不到公开注册设置且不会请求管理员接口', async () => {
    let calls = 0
    server.use(
      http.get('/admin/settings/registration', () => {
        calls += 1
        return HttpResponse.json({ enabled: true })
      }),
    )

    const { wrapper } = mountSecurity(regularUser)
    await flushPromises()

    expect(wrapper.find('[data-test="registration-setting"]').exists()).toBe(false)
    expect(calls).toBe(0)
    wrapper.unmount()
  })

  it('注册设置更新期间阻止重复操作并显示安全错误', async () => {
    const requestStarted = deferred()
    const releaseRequest = deferred()
    let calls = 0
    server.use(
      http.patch('/admin/settings/registration', async () => {
        calls += 1
        requestStarted.resolve()
        await releaseRequest.promise
        return apiError('registration_update_failed', 500)
      }),
    )
    const { wrapper } = mountSecurity()
    await flushPromises()

    await wrapper.get('[data-test="registration-toggle"]').trigger('click')
    await requestStarted.promise
    await wrapper.get('[data-test="registration-toggle"]').trigger('click')

    expect(calls).toBe(1)
    expect(wrapper.get('[data-test="registration-toggle"]').attributes('disabled')).toBeDefined()
    releaseRequest.resolve()
    await flushPromises()

    expect(wrapper.text()).toContain('服务暂时不可用')
    expect(wrapper.text()).not.toContain('The server message')
    expect(wrapper.get('[data-test="registration-setting"]').text()).toContain('已开启')
    wrapper.unmount()
  })

  it('本地校验改密必填项与确认密码，且不发送确认密码', async () => {
    const requests: unknown[] = []
    server.use(
      http.post('/auth/password', async ({ request }) => {
        requests.push(await request.json())
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { wrapper } = mountSecurity()

    await wrapper.findAll('form')[0]?.trigger('submit')
    expect(wrapper.get('[data-test="password-error"]').text()).toContain('请输入当前密码')

    await wrapper.get('[data-test="current-password"]').setValue('current-password')
    await wrapper.get('[data-test="new-password"]').setValue('replacement-password')
    await wrapper.get('[data-test="new-password-confirm"]').setValue('different-password')
    await wrapper.get('[data-test="change-password"]').trigger('click')

    expect(wrapper.get('[data-test="password-error"]').text()).toContain(
      '两次输入的新密码不一致',
    )
    expect(requests).toEqual([])
    expect((wrapper.vm as unknown as { currentPassword: string }).currentPassword).toBe('')
    expect((wrapper.vm as unknown as { newPassword: string }).newPassword).toBe('')
    expect(
      (wrapper.vm as unknown as { newPasswordConfirmation: string }).newPasswordConfirmation,
    ).toBe('')
    wrapper.unmount()
  })

  it('成功修改密码时只发送当前和新密码，并清空字段', async () => {
    const requests: unknown[] = []
    server.use(
      http.post('/auth/password', async ({ request }) => {
        requests.push(await request.json())
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { wrapper } = mountSecurity()
    await wrapper.get('[data-test="current-password"]').setValue('current-password')
    await wrapper.get('[data-test="new-password"]').setValue('replacement-password')
    await wrapper.get('[data-test="new-password-confirm"]').setValue('replacement-password')

    await wrapper.get('[data-test="change-password"]').trigger('click')
    await flushPromises()

    expect(requests).toEqual([
      { current_password: 'current-password', new_password: 'replacement-password' },
    ])
    expect(wrapper.text()).toContain('密码已修改')
    expect(wrapper.text()).not.toContain('current-password')
    expect(wrapper.text()).not.toContain('replacement-password')
    expect((wrapper.vm as unknown as { currentPassword: string }).currentPassword).toBe('')
    expect((wrapper.vm as unknown as { newPassword: string }).newPassword).toBe('')
    wrapper.unmount()
  })

  it('改密请求期间阻止重复提交，失败后清空所有密码并显示安全错误', async () => {
    const requestStarted = deferred()
    const releaseRequest = deferred()
    let calls = 0
    server.use(
      http.post('/auth/password', async () => {
        calls += 1
        requestStarted.resolve()
        await releaseRequest.promise
        return apiError('invalid_credentials', 401)
      }),
    )
    const { wrapper } = mountSecurity()
    await wrapper.get('[data-test="current-password"]').setValue('wrong-current-password')
    await wrapper.get('[data-test="new-password"]').setValue('replacement-password')
    await wrapper.get('[data-test="new-password-confirm"]').setValue('replacement-password')

    await wrapper.get('[data-test="change-password"]').trigger('click')
    await requestStarted.promise
    await wrapper.get('[data-test="change-password"]').trigger('click')
    expect(calls).toBe(1)
    expect(wrapper.get('[data-test="change-password"]').attributes('disabled')).toBeDefined()
    releaseRequest.resolve()
    await flushPromises()

    expect(wrapper.get('[data-test="password-error"]').text()).toContain('当前密码不正确')
    expect(wrapper.text()).not.toContain('The server message')
    expect((wrapper.vm as unknown as { currentPassword: string }).currentPassword).toBe('')
    expect((wrapper.vm as unknown as { newPassword: string }).newPassword).toBe('')
    expect(
      (wrapper.vm as unknown as { newPasswordConfirmation: string }).newPasswordConfirmation,
    ).toBe('')
    wrapper.unmount()
  })

  it('关闭 TOTP 时发送当前密码与六位码，刷新状态并清空凭据', async () => {
    const requests: unknown[] = []
    let disabled = false
    server.use(
      http.post('/auth/totp/disable', async ({ request }) => {
        requests.push(await request.json())
        disabled = true
        return HttpResponse.json({ totp_enabled: false })
      }),
      http.get('/auth/me', () => HttpResponse.json(disabled ? disabledAdmin : enabledAdmin)),
    )
    const { auth, wrapper } = mountSecurity(enabledAdmin)
    await wrapper.get('[data-test="disable-password"]').setValue('current-password')
    await wrapper.get('[data-test="disable-code"]').setValue('12a34 56')

    await wrapper.get('[data-test="disable-totp"]').trigger('click')
    await flushPromises()

    expect(requests).toEqual([{ current_password: 'current-password', code: '123456' }])
    expect(auth.user).toEqual(disabledAdmin)
    expect(wrapper.text()).toContain('双重验证已关闭')
    expect(wrapper.text()).toContain('未启用')
    expect((wrapper.vm as unknown as { disablePassword: string }).disablePassword).toBe('')
    expect((wrapper.vm as unknown as { disableCode: string }).disableCode).toBe('')
    wrapper.unmount()
  })

  it('退出或卸载会中止安全请求并清空改密与关闭 TOTP 凭据', async () => {
    const requestStarted = deferred()
    const releaseRequest = deferred()
    server.use(
      http.post('/auth/totp/disable', async () => {
        requestStarted.resolve()
        await releaseRequest.promise
        return HttpResponse.json({ totp_enabled: false })
      }),
    )
    const first = mountSecurity(enabledAdmin)
    await first.wrapper.get('[data-test="current-password"]').setValue('password-secret')
    await first.wrapper.get('[data-test="new-password"]').setValue('new-password-secret')
    await first.wrapper
      .get('[data-test="new-password-confirm"]')
      .setValue('new-password-secret')
    await first.wrapper.get('[data-test="disable-password"]').setValue('password-secret')
    await first.wrapper.get('[data-test="disable-code"]').setValue('123456')
    await first.wrapper.get('[data-test="disable-totp"]').trigger('click')
    await requestStarted.promise

    first.auth.logout()
    releaseRequest.resolve()
    await flushPromises()

    expect((first.wrapper.vm as unknown as { currentPassword: string }).currentPassword).toBe('')
    expect((first.wrapper.vm as unknown as { newPassword: string }).newPassword).toBe('')
    expect((first.wrapper.vm as unknown as { disablePassword: string }).disablePassword).toBe('')
    expect((first.wrapper.vm as unknown as { disableCode: string }).disableCode).toBe('')
    expect(first.wrapper.text()).not.toContain('双重验证已关闭')
    first.wrapper.unmount()

    const second = mountSecurity(enabledAdmin)
    await second.wrapper.get('[data-test="current-password"]').setValue('password-secret')
    await second.wrapper.get('[data-test="new-password"]').setValue('new-password-secret')
    await second.wrapper
      .get('[data-test="new-password-confirm"]')
      .setValue('new-password-secret')
    await second.wrapper.get('[data-test="disable-password"]').setValue('password-secret')
    await second.wrapper.get('[data-test="disable-code"]').setValue('654321')
    const vm = second.wrapper.vm as unknown as {
      currentPassword: string
      newPassword: string
      newPasswordConfirmation: string
      disablePassword: string
      disableCode: string
    }
    second.wrapper.unmount()

    expect(vm.currentPassword).toBe('')
    expect(vm.newPassword).toBe('')
    expect(vm.newPasswordConfirmation).toBe('')
    expect(vm.disablePassword).toBe('')
    expect(vm.disableCode).toBe('')
  })

  it('通过独立懒加载路由提供安全设置页面', async () => {
    const shellRoute = routes.find((route) => route.path === '/')
    const securityRoute = shellRoute?.children?.find((route) => route.name === 'security')
    if (typeof securityRoute?.component !== 'function') throw new Error('安全路由不是懒加载组件')

    const loadSecurity = securityRoute.component as () => Promise<{ default: unknown }>
    const loadedModule = await loadSecurity()

    expect(loadedModule.default).toBe(SecurityView)
  })

  it('首次启用发送空对象，setup 成功后才显示二维码，并以 /auth/me 刷新状态', async () => {
    const setupBodies: unknown[] = []
    const confirmBodies: unknown[] = []
    let confirmed = false
    server.use(
      http.post('/auth/totp/setup', async ({ request }) => {
        setupBodies.push(await request.json())
        return HttpResponse.json({ otpauth_uri: 'otpauth://totp/example?secret=setup-secret' })
      }),
      http.post('/auth/totp/confirm', async ({ request }) => {
        confirmBodies.push(await request.json())
        confirmed = true
        return HttpResponse.json({ totp_enabled: true })
      }),
      http.get('/auth/me', () => HttpResponse.json(confirmed ? enabledAdmin : disabledAdmin)),
    )
    const { auth, wrapper } = mountSecurity()

    expect(wrapper.findComponent(QrcodeVue).exists()).toBe(false)
    await wrapper.get('[data-test="start-totp"]').trigger('click')
    await flushPromises()

    expect(setupBodies).toEqual([{}])
    expect(wrapper.getComponent(QrcodeVue).props('value')).toBe(
      'otpauth://totp/example?secret=setup-secret',
    )
    expect((wrapper.get('[data-test="manual-uri"]').element as HTMLInputElement).value).toBe(
      'otpauth://totp/example?secret=setup-secret',
    )

    await wrapper.get('[data-test="confirm-code"]').setValue('12a34 56')
    expect((wrapper.get('[data-test="confirm-code"]').element as HTMLInputElement).value).toBe(
      '123456',
    )
    await wrapper.get('[data-test="confirm-totp"]').trigger('click')
    await flushPromises()

    expect(confirmBodies).toEqual([{ code: '123456' }])
    expect(auth.user).toEqual(enabledAdmin)
    expect(wrapper.findComponent(QrcodeVue).exists()).toBe(false)
    expect(wrapper.find('[data-test="manual-uri"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('双重验证已启用')
    wrapper.unmount()
  })

  it('重新绑定要求当前六位验证码，发送正确字段并在请求期间防止重复提交', async () => {
    const setupBodies: unknown[] = []
    const requestStarted = deferred()
    const releaseRequest = deferred()
    server.use(
      http.post('/auth/totp/setup', async ({ request }) => {
        setupBodies.push(await request.json())
        requestStarted.resolve()
        await releaseRequest.promise
        return HttpResponse.json({ otpauth_uri: 'otpauth://totp/replacement?secret=new-secret' })
      }),
    )
    const { wrapper } = mountSecurity(enabledAdmin)

    expect(wrapper.get('[data-test="start-totp"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="current-code"]').setValue('65x43 21')
    expect((wrapper.get('[data-test="current-code"]').element as HTMLInputElement).value).toBe(
      '654321',
    )

    await wrapper.get('[data-test="start-totp"]').trigger('click')
    await requestStarted.promise
    await wrapper.get('[data-test="start-totp"]').trigger('click')

    expect(setupBodies).toEqual([{ current_totp_code: '654321' }])
    expect(wrapper.get('[data-test="start-totp"]').attributes('disabled')).toBeDefined()
    releaseRequest.resolve()
    await flushPromises()
    expect(wrapper.findComponent(QrcodeVue).exists()).toBe(true)
    wrapper.unmount()
  })

  it.each([
    ['current_totp_required', '请输入当前六位验证码'],
    ['invalid_totp', '当前验证码无效，请重新输入'],
    ['totp_not_configured', '服务器未找到当前双重验证配置，请刷新后重试'],
  ])('将 setup 阶段的 %s 映射到当前验证码字段', async (code, message) => {
    server.use(http.post('/auth/totp/setup', () => apiError(code)))
    const { wrapper } = mountSecurity(enabledAdmin)

    await wrapper.get('[data-test="current-code"]').setValue('123456')
    await wrapper.get('[data-test="start-totp"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="current-code-error"]').text()).toBe(message)
    expect(wrapper.text()).not.toContain('The server message')
    expect((wrapper.get('[data-test="current-code"]').element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })

  it('本地状态未启用但服务端要求当前码时切换到换绑流程并允许重试', async () => {
    const setupBodies: unknown[] = []
    server.use(
      http.post('/auth/totp/setup', async ({ request }) => {
        const body = await request.json()
        setupBodies.push(body)
        if (setupBodies.length === 1) return apiError('current_totp_required')
        return HttpResponse.json({
          otpauth_uri: 'otpauth://totp/recovered?secret=replacement-secret',
        })
      }),
    )
    const { wrapper } = mountSecurity(disabledAdmin)

    expect(wrapper.find('[data-test="current-code"]').exists()).toBe(false)
    await wrapper.get('[data-test="start-totp"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="current-code-error"]').text()).toBe(
      '请输入当前六位验证码',
    )
    await wrapper.get('[data-test="current-code"]').setValue('654321')
    await wrapper.get('[data-test="start-totp"]').trigger('click')
    await flushPromises()

    expect(setupBodies).toEqual([{}, { current_totp_code: '654321' }])
    expect(wrapper.getComponent(QrcodeVue).props('value')).toBe(
      'otpauth://totp/recovered?secret=replacement-secret',
    )
    wrapper.unmount()
  })

  it.each([
    ['invalid_totp', '新验证码无效，请重新输入'],
    ['totp_not_configured', '双重验证配置已失效，请重新开始设置'],
    ['current_totp_required', '请重新验证当前验证码并开始设置'],
  ])('将 confirm 阶段的 %s 映射到新验证码字段', async (code, message) => {
    server.use(
      http.post('/auth/totp/setup', () =>
        HttpResponse.json({ otpauth_uri: 'otpauth://totp/example?secret=setup-secret' }),
      ),
      http.post('/auth/totp/confirm', () => apiError(code)),
    )
    const { wrapper } = mountSecurity()

    await wrapper.get('[data-test="start-totp"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="confirm-code"]').setValue('123456')
    await wrapper.get('[data-test="confirm-totp"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="confirm-code-error"]').text()).toBe(message)
    expect(wrapper.text()).not.toContain('The server message')
    expect((wrapper.get('[data-test="confirm-code"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.get('[data-test="confirm-totp"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="confirm-code"]').setValue('654321')
    expect(wrapper.get('[data-test="confirm-totp"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('取消、退出登录和组件卸载时同步清除 URI 与两个验证码', async () => {
    server.use(
      http.post('/auth/totp/setup', () =>
        HttpResponse.json({ otpauth_uri: 'otpauth://totp/replacement?secret=never-retain' }),
      ),
    )
    const first = mountSecurity(enabledAdmin)
    await first.wrapper.get('[data-test="current-code"]').setValue('654321')
    await first.wrapper.get('[data-test="start-totp"]').trigger('click')
    await flushPromises()
    await first.wrapper.get('[data-test="confirm-code"]').setValue('123456')
    await first.wrapper.get('[data-test="cancel-totp"]').trigger('click')

    expect(first.wrapper.findComponent(QrcodeVue).exists()).toBe(false)
    expect((first.wrapper.get('[data-test="current-code"]').element as HTMLInputElement).value).toBe(
      '',
    )

    await first.wrapper.get('[data-test="current-code"]').setValue('111111')
    await first.wrapper.get('[data-test="start-totp"]').trigger('click')
    await flushPromises()
    await first.wrapper.get('[data-test="confirm-code"]').setValue('222222')
    first.auth.logout()

    expect((first.wrapper.vm as unknown as { setupUri: string }).setupUri).toBe('')
    expect((first.wrapper.vm as unknown as { currentCode: string }).currentCode).toBe('')
    expect((first.wrapper.vm as unknown as { confirmCode: string }).confirmCode).toBe('')
    first.wrapper.unmount()

    const second = mountSecurity(enabledAdmin)
    await second.wrapper.get('[data-test="current-code"]').setValue('333333')
    await second.wrapper.get('[data-test="start-totp"]').trigger('click')
    await flushPromises()
    await second.wrapper.get('[data-test="confirm-code"]').setValue('444444')
    second.wrapper.unmount()

    expect((second.wrapper.vm as unknown as { setupUri: string }).setupUri).toBe('')
    expect((second.wrapper.vm as unknown as { currentCode: string }).currentCode).toBe('')
    expect((second.wrapper.vm as unknown as { confirmCode: string }).confirmCode).toBe('')
  })

  it('取消后忽略迟到的 setup 响应，不重新写入 URI', async () => {
    const requestStarted = deferred()
    const releaseRequest = deferred()
    server.use(
      http.post('/auth/totp/setup', async () => {
        requestStarted.resolve()
        await releaseRequest.promise
        return HttpResponse.json({ otpauth_uri: 'otpauth://totp/late?secret=late-secret' })
      }),
    )
    const { wrapper } = mountSecurity()

    await wrapper.get('[data-test="start-totp"]').trigger('click')
    await requestStarted.promise
    await wrapper.get('[data-test="cancel-setup"]').trigger('click')
    releaseRequest.resolve()
    await flushPromises()

    expect(wrapper.findComponent(QrcodeVue).exists()).toBe(false)
    expect((wrapper.vm as unknown as { setupUri: string }).setupUri).toBe('')
    wrapper.unmount()
  })

  it('取消后忽略迟到的 current_totp_required，不切换到换绑状态', async () => {
    const requestStarted = deferred()
    const releaseRequest = deferred()
    server.use(
      http.post('/auth/totp/setup', async () => {
        requestStarted.resolve()
        await releaseRequest.promise
        return apiError('current_totp_required')
      }),
    )
    const { wrapper } = mountSecurity(disabledAdmin)

    await wrapper.get('[data-test="start-totp"]').trigger('click')
    await requestStarted.promise
    await wrapper.get('[data-test="cancel-setup"]').trigger('click')
    releaseRequest.resolve()
    await flushPromises()

    expect(wrapper.find('[data-test="current-code"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="start-totp"]').text()).toBe('启用双重验证')
    wrapper.unmount()
  })

  it('确认后的 /auth/me 迟到响应不能在退出后恢复会话或敏感状态', async () => {
    const refreshStarted = deferred()
    const releaseRefresh = deferred()
    server.use(
      http.post('/auth/totp/setup', () =>
        HttpResponse.json({ otpauth_uri: 'otpauth://totp/example?secret=setup-secret' }),
      ),
      http.post('/auth/totp/confirm', () => HttpResponse.json({ totp_enabled: true })),
      http.get('/auth/me', async () => {
        refreshStarted.resolve()
        await releaseRefresh.promise
        return HttpResponse.json(enabledAdmin)
      }),
    )
    const { auth, wrapper } = mountSecurity()
    await wrapper.get('[data-test="start-totp"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="confirm-code"]').setValue('123456')
    await wrapper.get('[data-test="confirm-totp"]').trigger('click')
    await refreshStarted.promise

    auth.logout()
    releaseRefresh.resolve()
    await flushPromises()

    expect(auth.user).toBeNull()
    expect((wrapper.vm as unknown as { setupUri: string }).setupUri).toBe('')
    expect((wrapper.vm as unknown as { confirmCode: string }).confirmCode).toBe('')
    expect(wrapper.text()).not.toContain('双重验证已启用')
    wrapper.unmount()
  })
})
