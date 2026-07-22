import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessageBox, type MessageBoxData } from 'element-plus'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import type { LedgerEntryResponse, UserResponse } from '@/api/types'
import BalanceDialog from '@/components/users/BalanceDialog.vue'
import LedgerDrawer from '@/components/users/LedgerDrawer.vue'
import UserFormDrawer from '@/components/users/UserFormDrawer.vue'
import { routes } from '@/router'
import { useAuthStore } from '@/stores/auth'
import UsersView from '@/views/UsersView.vue'

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T) => void
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolver) => {
    resolve = resolver
  })
  return { promise, resolve }
}

const adminUser: UserResponse = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin',
  is_active: true,
  balance: '999999999999.99999999',
  total_spent: '0E-8',
  created_at: '2026-07-20T08:00:00Z',
  updated_at: '2026-07-21T08:00:00Z',
}

const memberUser: UserResponse = {
  id: 2,
  email: 'member@example.com',
  role: 'user',
  is_active: true,
  balance: '8.75000000',
  total_spent: '1.25000000',
  created_at: '2026-07-20T09:00:00Z',
  updated_at: '2026-07-21T09:00:00Z',
}

const ledgerEntries: LedgerEntryResponse[] = [
  {
    id: 12,
    request_id: null,
    idempotency_key: 'console-adjustment',
    kind: 'adjustment',
    amount: '10.25000000',
    balance_after: '19.00000000',
    metadata: { reason: '<img src=x onerror="globalThis.injected=true">' },
    created_at: '2026-07-22T09:00:00Z',
  },
  {
    id: 11,
    request_id: '11111111-1111-1111-1111-111111111111',
    idempotency_key: 'usage-request',
    kind: 'usage',
    amount: '-1.25000000',
    balance_after: '8.75000000',
    metadata: { nested: { source: 'provider' } },
    created_at: '2026-07-22T08:00:00Z',
  },
]

const server = setupServer()

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

afterEach(() => {
  vi.restoreAllMocks()
  server.resetHandlers()
  document.body.innerHTML = ''
})

afterAll(() => {
  server.close()
})

function useUserList(users: UserResponse[] = [adminUser, memberUser]): void {
  server.use(http.get('/admin/users', () => HttpResponse.json(users)))
}

async function mountUsers(users: UserResponse[] = [adminUser, memberUser]): Promise<VueWrapper> {
  useUserList(users)
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = {
    id: adminUser.id,
    email: adminUser.email,
    role: 'admin',
    is_active: true,
    totp_enabled: false,
    created_at: adminUser.created_at,
    updated_at: adminUser.updated_at,
  }
  const wrapper = mount(UsersView, {
    attachTo: document.body,
    global: { plugins: [pinia] },
  })
  await flushPromises()
  return wrapper
}

describe('用户、余额与账本管理', () => {
  it('通过独立懒加载路由提供用户页面', async () => {
    const shellRoute = routes.find((route) => route.path === '/')
    const userRoute = shellRoute?.children?.find((route) => route.name === 'users')
    if (typeof userRoute?.component !== 'function') throw new Error('用户路由不是懒加载组件')

    const loadUsers = userRoute.component as () => Promise<{ default: unknown }>
    const loadedModule = await loadUsers()
    expect(loadedModule.default).toBe(UsersView)
  })

  it('原样显示精确与科学记数金额，并禁止当前管理员停用或删除自己', async () => {
    const wrapper = await mountUsers()

    expect(wrapper.text()).toContain('999999999999.99999999')
    expect(wrapper.text()).toContain('0E-8')
    expect(wrapper.text()).toContain('8.75000000')
    expect(wrapper.text()).toContain('1.25000000')
    expect(wrapper.get('[data-test="edit-user-1"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-test="delete-user-1"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-test="edit-user-1"]').trigger('click')
    const drawer = wrapper.getComponent(UserFormDrawer)
    expect(drawer.get('[data-test="user-active"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('编辑时省略空白密码，并在关闭时立即清除密码草稿', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(UserFormDrawer, {
      props: {
        modelValue: true,
        user: memberUser,
        submitting: false,
        currentUserId: adminUser.id,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    const password = wrapper.get('[data-test="user-password"]')
    await password.setValue('   ')
    await wrapper.get('[data-test="user-email"]').setValue('renamed@example.com')
    await wrapper.get('[data-test="user-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({ email: 'renamed@example.com' })
    await password.setValue('never-retain-this')
    await wrapper.get('[data-test="user-cancel"]').trigger('click')
    expect(password.element).toHaveProperty('value', '')
    wrapper.unmount()
  })

  it('创建用户时原样提交初始余额字符串，不经过浮点数转换', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(UserFormDrawer, {
      props: {
        modelValue: true,
        user: null,
        submitting: false,
        currentUserId: adminUser.id,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="user-email"]').setValue('new@example.com')
    await wrapper.get('[data-test="user-password"]').setValue('new-user-password')
    await wrapper.get('[data-test="user-initial-balance"]').setValue('999999999999.99999999')
    await wrapper.get('[data-test="user-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({
      email: 'new@example.com',
      password: 'new-user-password',
      role: 'user',
      initial_balance: '999999999999.99999999',
    })
    wrapper.unmount()
  })

  it('拒绝零、负零和科学记数调整，同时接受精确的带符号小数', async () => {
    const onSubmit = vi.fn()
    const uuid = vi
      .spyOn(crypto, 'randomUUID')
      .mockReturnValue('11111111-1111-4111-8111-111111111111')
    const wrapper = mount(BalanceDialog, {
      props: { modelValue: true, user: memberUser, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    for (const invalid of ['0', '-0.00000000', '1e-8']) {
      await wrapper.get('[data-test="balance-amount"]').setValue(invalid)
      await wrapper.get('[data-test="balance-reason"]').setValue('人工充值')
      await wrapper.get('[data-test="balance-submit"]').trigger('click')
      expect(onSubmit).not.toHaveBeenCalled()
    }

    await wrapper.get('[data-test="balance-amount"]').setValue('-10.25000000')
    await wrapper.get('[data-test="balance-submit"]').trigger('click')
    expect(wrapper.text()).toContain('扣减')
    expect(onSubmit).toHaveBeenCalledWith({
      amount: '-10.25000000',
      reason: '人工充值',
      idempotency_key: 'console-11111111-1111-4111-8111-111111111111',
    })
    expect(uuid).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('余额调整失败重试复用同一幂等键，关闭后新会话生成新键并清空输入', async () => {
    const requests: unknown[] = []
    vi.spyOn(crypto, 'randomUUID')
      .mockReturnValueOnce('11111111-1111-4111-8111-111111111111')
      .mockReturnValueOnce('22222222-2222-4222-8222-222222222222')
    let attempts = 0
    server.use(
      http.post('/admin/users/2/balance-adjustments', async ({ request }) => {
        requests.push(await request.json())
        attempts += 1
        if (attempts === 1) {
          return HttpResponse.json(
            { detail: { code: 'temporary_failure', message: '请重试' } },
            { status: 503 },
          )
        }
        return HttpResponse.json(
          {
            ledger_entry_id: attempts,
            amount: '10.25000000',
            balance: '19.00000000',
            total_spent: '1.25000000',
          },
          { status: 201 },
        )
      }),
    )
    const wrapper = await mountUsers()

    await wrapper.get('[data-test="adjust-user-2"]').trigger('click')
    let dialog = wrapper.getComponent(BalanceDialog)
    await dialog.get('[data-test="balance-amount"]').setValue('10.25000000')
    await dialog.get('[data-test="balance-reason"]').setValue('人工充值')
    await dialog.get('[data-test="balance-submit"]').trigger('click')
    await flushPromises()
    await dialog.get('[data-test="balance-submit"]').trigger('click')
    await flushPromises()

    expect(requests).toHaveLength(2)
    expect(requests[0]).toEqual(requests[1])
    expect(requests[0]).toMatchObject({
      amount: '10.25000000',
      reason: '人工充值',
      idempotency_key: 'console-11111111-1111-4111-8111-111111111111',
    })
    expect(wrapper.text()).toContain('19.00000000')
    expect(wrapper.text()).toContain('1.25000000')

    await wrapper.get('[data-test="adjust-user-2"]').trigger('click')
    dialog = wrapper.getComponent(BalanceDialog)
    expect(dialog.get('[data-test="balance-amount"]').element).toHaveProperty('value', '')
    expect(dialog.get('[data-test="balance-reason"]').element).toHaveProperty('value', '')
    await dialog.get('[data-test="balance-amount"]').setValue('1.00000000')
    await dialog.get('[data-test="balance-reason"]').setValue('再次充值')
    await dialog.get('[data-test="balance-submit"]').trigger('click')
    await flushPromises()
    expect(requests[2]).toMatchObject({
      idempotency_key: 'console-22222222-2222-4222-8222-222222222222',
    })
    wrapper.unmount()
  })

  it('账本按倒序展示完整字段，并把恶意元数据作为纯文本渲染', async () => {
    const wrapper = mount(LedgerDrawer, {
      props: {
        modelValue: true,
        user: memberUser,
        entries: [...ledgerEntries].reverse(),
        loading: false,
        error: '',
      },
      attachTo: document.body,
    })
    await flushPromises()

    const rows = wrapper.findAll('[data-test^="ledger-row-"]')
    expect(rows.map((row) => row.attributes('data-test'))).toEqual([
      'ledger-row-12',
      'ledger-row-11',
    ])
    expect(wrapper.text()).toContain('10.25000000')
    expect(wrapper.text()).toContain('19.00000000')
    expect(wrapper.text()).toContain('11111111-1111-1111-1111-111111111111')
    expect(wrapper.text()).toContain('<img src=x onerror=')
    expect(wrapper.find('img').exists()).toBe(false)
    wrapper.unmount()
  })

  it('同一用户删除确认期间排除编辑、调账和账本操作', async () => {
    const confirmation = deferred<MessageBoxData>()
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockReturnValue(confirmation.promise)
    const wrapper = await mountUsers()

    const deleteButton = wrapper.get('[data-test="delete-user-2"]')
    await Promise.all([deleteButton.trigger('click'), deleteButton.trigger('click')])
    await wrapper.get('[data-test="edit-user-2"]').trigger('click')
    await wrapper.get('[data-test="adjust-user-2"]').trigger('click')
    await wrapper.get('[data-test="ledger-user-2"]').trigger('click')

    expect(confirm).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-test="edit-user-2"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="adjust-user-2"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="ledger-user-2"]').attributes('disabled')).toBeDefined()
    expect(wrapper.findComponent(UserFormDrawer).props('modelValue')).toBe(false)
    expect(wrapper.findComponent(BalanceDialog).props('modelValue')).toBe(false)

    wrapper.unmount()
    confirmation.resolve({ value: '', action: 'confirm' } as MessageBoxData)
    await flushPromises()
  })

  it('保存期间锁定用户抽屉并让卸载后的响应失效', async () => {
    const patchResponse = deferred<UserResponse>()
    server.use(
      http.patch('/admin/users/2', async () => HttpResponse.json(await patchResponse.promise)),
    )
    const wrapper = await mountUsers()

    await wrapper.get('[data-test="edit-user-2"]').trigger('click')
    const drawer = wrapper.getComponent(UserFormDrawer)
    await drawer.get('[data-test="user-email"]').setValue('delayed@example.com')
    await drawer.get('[data-test="user-password"]').setValue('transient-password')
    await drawer.get('[data-test="user-submit"]').trigger('click')
    await flushPromises()

    expect(drawer.get('[data-test="user-cancel"]').attributes('disabled')).toBeDefined()
    expect(drawer.find('.el-drawer__close-btn').exists()).toBe(false)
    await drawer.get('[data-test="user-cancel"]').trigger('click')
    await wrapper.get('[data-test="create-user"]').trigger('click')
    expect(drawer.text()).toContain('编辑用户')
    expect(drawer.get('[data-test="user-email"]').element).toHaveProperty(
      'value',
      'delayed@example.com',
    )

    wrapper.unmount()
    patchResponse.resolve({ ...memberUser, email: 'delayed@example.com' })
    await flushPromises()
    expect(document.querySelector('[data-test="user-notice"]')).toBeNull()
    expect(document.body.textContent).not.toContain('用户设置已保存')
  })

  it('删除成功后忽略更早发出的列表响应，不恢复已删除用户', async () => {
    const staleList = deferred<UserResponse[]>()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(http.delete('/admin/users/2', () => new HttpResponse(null, { status: 204 })))
    const wrapper = await mountUsers()
    server.use(http.get('/admin/users', async () => HttpResponse.json(await staleList.promise)))

    await wrapper.get('[aria-label="刷新用户列表"]').trigger('click')
    await wrapper.get('[data-test="delete-user-2"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="delete-user-2"]').exists()).toBe(false)

    staleList.resolve([adminUser, memberUser])
    await flushPromises()
    expect(wrapper.find('[data-test="delete-user-2"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
