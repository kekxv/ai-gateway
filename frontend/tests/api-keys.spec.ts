import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElDialog, ElMessageBox, type MessageBoxData } from 'element-plus'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { listApiKeys } from '@/api/apiKeys'
import type {
  ApiKeyCreate,
  ApiKeyResponse,
  ApiKeyScope,
  ApiKeyUpdate,
  ModelResponse,
  ProviderResponse,
  UserResponse,
} from '@/api/types'
import ApiKeyFormDrawer from '@/components/api-keys/ApiKeyFormDrawer.vue'
import SecretResultDialog from '@/components/api-keys/SecretResultDialog.vue'
import { routes } from '@/router'
import ApiKeysView from '@/views/ApiKeysView.vue'

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

const users: UserResponse[] = [
  {
    id: 1,
    email: 'admin@example.com',
    role: 'admin',
    is_active: true,
    balance: '100.00000000',
    total_spent: '0E-8',
    created_at: '2026-07-20T08:00:00Z',
    updated_at: '2026-07-21T08:00:00Z',
  },
  {
    id: 2,
    email: 'member@example.com',
    role: 'user',
    is_active: true,
    balance: '8.75000000',
    total_spent: '1.25000000',
    created_at: '2026-07-20T09:00:00Z',
    updated_at: '2026-07-21T09:00:00Z',
  },
]

const providers: ProviderResponse[] = [
  {
    id: 11,
    name: '主线路',
    has_credential: true,
    enabled: true,
    auto_load_models: false,
    model_sync_interval_seconds: 3600,
    last_model_sync_at: null,
    price_multiplier: 1.0,
    protocols: [],
  },
  {
    id: 12,
    name: '备用线路',
    has_credential: true,
    enabled: true,
    auto_load_models: false,
    model_sync_interval_seconds: 3600,
    last_model_sync_at: null,
    price_multiplier: 1.0,
    protocols: [],
  },
]

const models: ModelResponse[] = [
  {
    id: 21,
    canonical_name: 'gpt-4.1',
    display_name: 'GPT 4.1',
    input_price_per_million: '2.00000000',
    output_price_per_million: '8.00000000',
    cache_read_price_per_million: '0.00000000',
    cache_write_price_per_million: '0.00000000',
    price_multiplier: 1.0,
    enabled: true,
    aliases: [],
    routing_strategy: 'weighted_random',
    created_at: '2026-07-20T08:00:00Z',
    updated_at: '2026-07-21T08:00:00Z',
  },
  {
    id: 22,
    canonical_name: 'claude-opus',
    display_name: 'Claude Opus',
    input_price_per_million: '15.00000000',
    output_price_per_million: '75.00000000',
    cache_read_price_per_million: '0.00000000',
    cache_write_price_per_million: '0.00000000',
    price_multiplier: 1.0,
    enabled: true,
    aliases: [],
    routing_strategy: 'weighted_random',
    created_at: '2026-07-20T08:00:00Z',
    updated_at: '2026-07-21T08:00:00Z',
  },
]

const activeKey: ApiKeyResponse = {
  id: 31,
  user_id: 2,
  name: '生产调用',
  key_prefix: 'sk-gw-prod12',
  scope: 'providers',
  is_active: true,
  expires_at: '2026-12-31T16:00:00Z',
  last_used_at: '2026-07-22T08:00:00Z',
  created_at: '2026-07-20T08:00:00Z',
  provider_ids: [11],
  model_ids: [],
}

const secondActiveKey: ApiKeyResponse = {
  ...activeKey,
  id: 32,
  name: '测试调用',
  key_prefix: 'sk-gw-test12',
}

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

function useCatalog(keys: ApiKeyResponse[] = [activeKey]): void {
  server.use(
    http.get('/admin/api-keys', () => HttpResponse.json(keys)),
    http.get('/admin/users', () => HttpResponse.json(users)),
    http.get('/admin/providers', () => HttpResponse.json(providers)),
    http.get('/admin/models', () => HttpResponse.json(models)),
  )
}

async function mountKeys(keys: ApiKeyResponse[] = [activeKey]): Promise<VueWrapper> {
  useCatalog(keys)
  const wrapper = mount(ApiKeysView, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

function mountForm(
  key: ApiKeyResponse | null = null,
  onSubmit = vi.fn<(payload: ApiKeyCreate | ApiKeyUpdate) => void>(),
) {
  return {
    wrapper: mount(ApiKeyFormDrawer, {
      props: {
        modelValue: true,
        apiKey: key,
        users,
        providers,
        models,
        submitting: false,
        onSubmit,
      },
      attachTo: document.body,
    }),
    onSubmit,
  }
}

describe('接口密钥作用域与一次性明文', () => {
  it('通过本地懒加载路由提供接口密钥页面', async () => {
    const shellRoute = routes.find((route) => route.path === '/')
    const apiKeyRoute = shellRoute?.children?.find((route) => route.name === 'api-keys')
    if (typeof apiKeyRoute?.component !== 'function') throw new Error('密钥路由不是懒加载组件')

    const loadApiKeys = apiKeyRoute.component as () => Promise<{ default: unknown }>
    const loadedModule = await loadApiKeys()
    expect(loadedModule.default).toBe(ApiKeysView)
  })

  it('仅在提供 userId 时序列化精确的 owner filter', async () => {
    const urls: URL[] = []
    server.use(
      http.get('/admin/api-keys', ({ request }) => {
        urls.push(new URL(request.url))
        return HttpResponse.json([])
      }),
    )

    await listApiKeys()
    await listApiKeys(2)

    expect(urls[0]?.search).toBe('')
    expect(urls[1]?.searchParams.get('user_id')).toBe('2')
  })

  it.each<[ApiKeyScope, boolean, boolean]>([
    ['all', false, false],
    ['providers', true, false],
    ['models', false, true],
    ['providers_and_models', true, true],
  ])('作用域 %s 只显示相关必选器', async (scope, providersVisible, modelsVisible) => {
    const { wrapper } = mountForm()
    await flushPromises()
    await wrapper.get('[data-test="api-key-scope"]').setValue(scope)

    expect(wrapper.find('[data-test="api-key-provider-11"]').exists()).toBe(providersVisible)
    expect(wrapper.find('[data-test="api-key-model-21"]').exists()).toBe(modelsVisible)
    wrapper.unmount()
  })

  it('切换作用域立即清除无关数组，并按 ISO/null 语义创建', async () => {
    const { wrapper, onSubmit } = mountForm()
    await flushPromises()
    await wrapper.get('[data-test="api-key-name"]').setValue('  移动端  ')
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    expect(onSubmit).not.toHaveBeenCalled()

    await wrapper.get('[data-test="api-key-owner"]').setValue('2')
    await wrapper.get('[data-test="api-key-scope"]').setValue('providers_and_models')
    await wrapper.get<HTMLInputElement>('[data-test="api-key-provider-11"]').setValue(true)
    await wrapper.get<HTMLInputElement>('[data-test="api-key-model-21"]').setValue(true)
    await wrapper.get('[data-test="api-key-scope"]').setValue('models')
    expect(wrapper.find('[data-test="api-key-provider-11"]').exists()).toBe(false)
    await wrapper.get('[data-test="api-key-scope"]').setValue('providers_and_models')
    expect(wrapper.get<HTMLInputElement>('[data-test="api-key-provider-11"]').element.checked).toBe(false)
    expect(wrapper.get<HTMLInputElement>('[data-test="api-key-model-21"]').element.checked).toBe(true)
    await wrapper.get('[data-test="api-key-scope"]').setValue('models')
    await wrapper.get('[data-test="api-key-expiry"]').setValue('2030-01-02T03:04')
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({
      user_id: 2,
      name: '移动端',
      scope: 'models',
      is_active: true,
      expires_at: new Date('2030-01-02T03:04').toISOString(),
      provider_ids: [],
      model_ids: [21],
    })

    await wrapper.get('[data-test="api-key-expiry"]').setValue('')
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    expect(onSubmit).toHaveBeenLastCalledWith(expect.objectContaining({ expires_at: null }))
    wrapper.unmount()
  })

  it('编辑 owner 精确映射且仅 PATCH 脏字段，清空过期时间显式发送 null', async () => {
    const { wrapper, onSubmit } = mountForm(activeKey)
    await flushPromises()

    expect(wrapper.get<HTMLSelectElement>('[data-test="api-key-owner"]').element.value).toBe('2')
    expect(wrapper.get('[data-test="api-key-owner"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    expect(onSubmit).toHaveBeenCalledWith({})

    await wrapper.get('[data-test="api-key-name"]').setValue('生产调用 v2')
    await wrapper.get('[data-test="api-key-expiry"]').setValue('')
    await wrapper.get('[data-test="api-key-scope"]').setValue('all')
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    expect(onSubmit).toHaveBeenLastCalledWith({
      name: '生产调用 v2',
      scope: 'all',
      expires_at: null,
      provider_ids: [],
      model_ids: [],
    })
    wrapper.unmount()
  })

  it('所有者原生选择框与可见标签有程序化关联', async () => {
    const { wrapper } = mountForm()
    await flushPromises()

    const ownerSelect = wrapper.get('[data-test="api-key-owner"]')
    expect(ownerSelect.attributes('id')).toBe('api-key-owner')
    const ownerLabel = wrapper.find('label[for="api-key-owner"]')
    expect(ownerLabel.exists()).toBe(true)
    expect(ownerLabel.text()).toContain('所有者')
    wrapper.unmount()
  })

  it('未编辑非整分钟过期时间时保留秒和毫秒精度，清空或真实修改仍发送', async () => {
    const preciseExpiryKey: ApiKeyResponse = {
      ...activeKey,
      expires_at: '2026-12-31T16:00:37.789Z',
    }
    const { wrapper, onSubmit } = mountForm(preciseExpiryKey)
    await flushPromises()

    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    expect(onSubmit).toHaveBeenLastCalledWith({})

    await wrapper.get('[data-test="api-key-expiry"]').setValue('')
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    expect(onSubmit).toHaveBeenLastCalledWith({ expires_at: null })

    await wrapper.get('[data-test="api-key-expiry"]').setValue('2030-05-06T07:08')
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    expect(onSubmit).toHaveBeenLastCalledWith({
      expires_at: new Date('2030-05-06T07:08').toISOString(),
    })
    wrapper.unmount()
  })

  it('表格按 user_id 精确显示 owner email，而非数组位置', async () => {
    const wrapper = await mountKeys()
    expect(wrapper.get('[data-test="api-key-row-31"]').text()).toContain('member@example.com')
    expect(wrapper.get('[data-test="api-key-row-31"]').text()).not.toContain('admin@example.com')
    wrapper.unmount()
  })

  it('一次性对话框禁止遮罩/ESC/标题关闭，确认前不能关闭', async () => {
    const onClose = vi.fn()
    const wrapper = mount(SecretResultDialog, {
      props: {
        modelValue: true,
        secret: 'sk-gw-once-only',
        onClose,
      },
      attachTo: document.body,
    })
    await flushPromises()

    const dialog = wrapper.getComponent(ElDialog)
    expect(dialog.props('closeOnClickModal')).toBe(false)
    expect(dialog.props('closeOnPressEscape')).toBe(false)
    expect(dialog.props('showClose')).toBe(false)
    expect(wrapper.get('[data-test="secret-confirm-close"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="secret-confirm-close"]').trigger('click')
    expect(onClose).not.toHaveBeenCalled()

    await wrapper.get('[data-test="secret-acknowledged"] input').setValue(true)
    await wrapper.get('[data-test="secret-confirm-close"]').trigger('click')
    expect(onClose).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('复制不经通知传递密钥，下载后立即撤销对象 URL', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    const createObjectURL = vi.fn().mockReturnValue('blob:one-time-secret')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const wrapper = mount(SecretResultDialog, {
      props: { modelValue: true, secret: 'sk-gw-download-once' },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="secret-copy"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('sk-gw-download-once')
    expect(wrapper.text()).toContain('已复制')
    expect(wrapper.text().match(/sk-gw-download-once/g)).toHaveLength(1)
    expect(wrapper.text()).toContain('$AI_GATEWAY_API_KEY')

    await wrapper.get('[data-test="secret-download"]').trigger('click')
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(anchorClick).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:one-time-secret')
    wrapper.unmount()
    expect(revokeObjectURL).toHaveBeenCalledTimes(1)
  })

  it('创建响应只把 metadata 加入列表，确认关闭后 DOM 与父组件状态都清除明文', async () => {
    let received: unknown
    useCatalog([])
    server.use(
      http.post('/admin/api-keys', async ({ request }) => {
        received = await request.json()
        return HttpResponse.json(
          {
            ...activeKey,
            id: 32,
            name: '新密钥',
            key_prefix: 'sk-gw-new123',
            key: 'sk-gw-once-only',
          },
          { status: 201 },
        )
      }),
    )
    const wrapper = mount(ApiKeysView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="create-api-key"]').trigger('click')
    await wrapper.get('[data-test="api-key-owner"]').setValue('2')
    await wrapper.get('[data-test="api-key-name"]').setValue('新密钥')
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    await flushPromises()

    expect(received).toMatchObject({ user_id: 2, name: '新密钥', expires_at: null })
    expect(wrapper.text()).toContain('sk-gw-once-only')
    expect(wrapper.text().match(/sk-gw-once-only/g)).toHaveLength(1)
    expect(wrapper.get('[data-test="api-key-row-32"]').text()).not.toContain('sk-gw-once-only')
    await wrapper.get('[data-test="secret-acknowledged"] input').setValue(true)
    await wrapper.get('[data-test="secret-confirm-close"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('sk-gw-once-only')
    expect(wrapper.findComponent(SecretResultDialog).props('secret')).toBeNull()
    wrapper.unmount()
  })

  it('轮换先确认旧密钥会停用，阻止并发并用 replacement metadata 替换旧行', async () => {
    const gate = deferred<Response>()
    let calls = 0
    useCatalog()
    server.use(
      http.post('/admin/api-keys/31/rotate', () => {
        calls += 1
        return gate.promise
      }),
    )
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as MessageBoxData)
    const wrapper = mount(ApiKeysView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="rotate-api-key-31"]').trigger('click')
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('旧密钥将立即停用'),
      expect.any(String),
      expect.any(Object),
    )
    await wrapper.get('[data-test="rotate-api-key-31"]').trigger('click')
    expect(calls).toBe(1)

    gate.resolve(
      HttpResponse.json(
        {
          ...activeKey,
          id: 41,
          key_prefix: 'sk-gw-rot123',
          key: 'sk-gw-rotated-once',
        },
        { status: 201 },
      ),
    )
    await flushPromises()
    expect(wrapper.find('[data-test="api-key-row-31"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="api-key-row-41"]').text()).toContain('sk-gw-ro****')
    expect(wrapper.text()).toContain('sk-gw-rotated-once')
    wrapper.unmount()
  })

  it('创建开始后全局独占明文生命周期，轮换不能交错覆盖创建结果', async () => {
    const createGate = deferred<Response>()
    let rotateCalls = 0
    useCatalog([activeKey])
    server.use(
      http.post('/admin/api-keys', () => createGate.promise),
      http.post('/admin/api-keys/31/rotate', () => {
        rotateCalls += 1
        return HttpResponse.json(
          { ...activeKey, id: 41, key: 'sk-gw-must-not-overwrite-create' },
          { status: 201 },
        )
      }),
    )
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as MessageBoxData)
    const wrapper = mount(ApiKeysView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="create-api-key"]').trigger('click')
    await wrapper.get('[data-test="api-key-owner"]').setValue('2')
    await wrapper.get('[data-test="api-key-name"]').setValue('创建独占')
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="rotate-api-key-31"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="rotate-api-key-31"]').trigger('click')
    expect(confirm).not.toHaveBeenCalled()
    expect(rotateCalls).toBe(0)

    createGate.resolve(
      HttpResponse.json(
        { ...activeKey, id: 42, key: 'sk-gw-created-exclusive' },
        { status: 201 },
      ),
    )
    await flushPromises()
    expect(wrapper.text()).toContain('sk-gw-created-exclusive')
    await wrapper.get('[data-test="rotate-api-key-31"]').trigger('click')
    expect(rotateCalls).toBe(0)
    expect(wrapper.text()).not.toContain('sk-gw-must-not-overwrite-create')

    await wrapper.get('[data-test="secret-acknowledged"] input').setValue(true)
    await wrapper.get('[data-test="secret-confirm-close"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="rotate-api-key-31"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('一个 key 开始轮换后全局独占，不同 key 的轮换不能交错覆盖结果', async () => {
    const firstRotateGate = deferred<Response>()
    let firstCalls = 0
    let secondCalls = 0
    useCatalog([activeKey, secondActiveKey])
    server.use(
      http.post('/admin/api-keys/31/rotate', () => {
        firstCalls += 1
        return firstRotateGate.promise
      }),
      http.post('/admin/api-keys/32/rotate', () => {
        secondCalls += 1
        return HttpResponse.json(
          { ...secondActiveKey, id: 52, key: 'sk-gw-second-must-not-render' },
          { status: 201 },
        )
      }),
    )
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as MessageBoxData)
    const wrapper = mount(ApiKeysView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="rotate-api-key-31"]').trigger('click')
    await flushPromises()
    expect(firstCalls).toBe(1)
    expect(wrapper.get('[data-test="rotate-api-key-32"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="rotate-api-key-32"]').trigger('click')
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(secondCalls).toBe(0)

    firstRotateGate.resolve(
      HttpResponse.json(
        { ...activeKey, id: 51, key: 'sk-gw-first-exclusive' },
        { status: 201 },
      ),
    )
    await flushPromises()
    expect(wrapper.text()).toContain('sk-gw-first-exclusive')
    await wrapper.get('[data-test="rotate-api-key-32"]').trigger('click')
    expect(secondCalls).toBe(0)
    expect(wrapper.text()).not.toContain('sk-gw-second-must-not-render')

    await wrapper.get('[data-test="secret-acknowledged"] input').setValue(true)
    await wrapper.get('[data-test="secret-confirm-close"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="rotate-api-key-32"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('轮换确认取消和请求失败都会释放全局明文租约', async () => {
    let rotateCalls = 0
    useCatalog([activeKey, secondActiveKey])
    server.use(
      http.post('/admin/api-keys/31/rotate', () => {
        rotateCalls += 1
        return HttpResponse.json(
          { detail: { code: 'temporary_failure', message: 'retry later' } },
          { status: 500 },
        )
      }),
    )
    vi.spyOn(ElMessageBox, 'confirm')
      .mockRejectedValueOnce(new Error('cancelled'))
      .mockResolvedValueOnce({} as MessageBoxData)
    const wrapper = mount(ApiKeysView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="rotate-api-key-31"]').trigger('click')
    await flushPromises()
    expect(rotateCalls).toBe(0)
    expect(wrapper.get('[data-test="create-api-key"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-test="rotate-api-key-32"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-test="rotate-api-key-31"]').trigger('click')
    await flushPromises()
    expect(rotateCalls).toBe(1)
    expect(wrapper.text()).toContain('服务暂时不可用')
    expect(wrapper.get('[data-test="create-api-key"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-test="rotate-api-key-32"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('inactive 轮换刷新表格并指导只能轮换启用密钥', async () => {
    let listCalls = 0
    server.use(
      http.get('/admin/api-keys', () => {
        listCalls += 1
        return HttpResponse.json([{ ...activeKey, is_active: listCalls === 1 }])
      }),
      http.get('/admin/users', () => HttpResponse.json(users)),
      http.get('/admin/providers', () => HttpResponse.json(providers)),
      http.get('/admin/models', () => HttpResponse.json(models)),
      http.post('/admin/api-keys/31/rotate', () =>
        HttpResponse.json(
          { detail: { code: 'api_key_inactive', message: 'Only active keys rotate' } },
          { status: 409 },
        ),
      ),
    )
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as MessageBoxData)
    const wrapper = mount(ApiKeysView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="rotate-api-key-31"]').trigger('click')
    await flushPromises()
    expect(listCalls).toBe(2)
    expect(wrapper.text()).toContain('只有启用中的密钥可以轮换')
    expect(wrapper.get('[data-test="api-key-row-31"]').text()).toContain('停用')
    wrapper.unmount()
  })

  it('忽略早于本地编辑完成的迟到列表，避免旧 metadata 回滚', async () => {
    const staleList = deferred<Response>()
    let listCalls = 0
    server.use(
      http.get('/admin/api-keys', () => {
        listCalls += 1
        if (listCalls === 1) return HttpResponse.json([activeKey])
        return staleList.promise
      }),
      http.get('/admin/users', () => HttpResponse.json(users)),
      http.get('/admin/providers', () => HttpResponse.json(providers)),
      http.get('/admin/models', () => HttpResponse.json(models)),
      http.patch('/admin/api-keys/31', () =>
        HttpResponse.json({ ...activeKey, name: '本地已更新名称' }),
      ),
    )
    const wrapper = mount(ApiKeysView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="refresh-api-keys"]').trigger('click')
    await wrapper.get('[data-test="edit-api-key-31"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="api-key-name"]').setValue('本地已更新名称')
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="api-key-row-31"]').text()).toContain('本地已更新名称')

    staleList.resolve(HttpResponse.json([activeKey]))
    await flushPromises()
    expect(wrapper.get('[data-test="api-key-row-31"]').text()).toContain('本地已更新名称')
    wrapper.unmount()
  })

  it('本地编辑成功后忽略较早列表的迟到失败并继续显示有效列表', async () => {
    const staleList = deferred<Response>()
    let listCalls = 0
    server.use(
      http.get('/admin/api-keys', () => {
        listCalls += 1
        if (listCalls === 1) return HttpResponse.json([activeKey])
        return staleList.promise
      }),
      http.get('/admin/users', () => HttpResponse.json(users)),
      http.get('/admin/providers', () => HttpResponse.json(providers)),
      http.get('/admin/models', () => HttpResponse.json(models)),
      http.patch('/admin/api-keys/31', () =>
        HttpResponse.json({ ...activeKey, name: '本地已更新名称' }),
      ),
    )
    const wrapper = mount(ApiKeysView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="refresh-api-keys"]').trigger('click')
    await wrapper.get('[data-test="edit-api-key-31"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="api-key-name"]').setValue('本地已更新名称')
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    await flushPromises()
    staleList.resolve(HttpResponse.json(null, { status: 500 }))
    await flushPromises()

    expect(wrapper.get('[data-test="api-key-row-31"]').text()).toContain('本地已更新名称')
    expect(wrapper.text()).not.toContain('接口密钥列表加载失败')
    wrapper.unmount()
  })

  it('创建请求进行中卸载会 abort，迟到 secret 响应不能进入 DOM', async () => {
    const createGate = deferred<Response>()
    const abortSpy = vi.spyOn(AbortController.prototype, 'abort')
    useCatalog([])
    server.use(
      http.post('/admin/api-keys', () => createGate.promise),
    )
    const wrapper = mount(ApiKeysView, { attachTo: document.body })
    await flushPromises()
    await wrapper.get('[data-test="create-api-key"]').trigger('click')
    await wrapper.get('[data-test="api-key-owner"]').setValue('2')
    await wrapper.get('[data-test="api-key-name"]').setValue('卸载中的创建')
    await wrapper.get('[data-test="api-key-submit"]').trigger('click')
    await flushPromises()

    wrapper.unmount()
    await flushPromises()
    expect(abortSpy).toHaveBeenCalled()
    createGate.resolve(
      HttpResponse.json(
        { ...activeKey, id: 99, key: 'sk-gw-must-never-render' },
        { status: 201 },
      ),
    )
    await flushPromises()
    expect(document.body.textContent).not.toContain('sk-gw-must-never-render')
  })

  it('卸载会中止控制器并令确认 continuation 与迟到加载失效', async () => {
    const loadGate = deferred<Response>()
    let deleteCalls = 0
    server.use(
      http.get('/admin/api-keys', () => loadGate.promise),
      http.get('/admin/users', () => HttpResponse.json(users)),
      http.get('/admin/providers', () => HttpResponse.json(providers)),
      http.get('/admin/models', () => HttpResponse.json(models)),
      http.delete('/admin/api-keys/31', () => {
        deleteCalls += 1
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const confirmGate = deferred<MessageBoxData>()
    vi.spyOn(ElMessageBox, 'confirm').mockReturnValue(confirmGate.promise)
    const wrapper = mount(ApiKeysView, { attachTo: document.body })
    await flushPromises()
    // The key is not available while the load is pending, so resolve once, then open confirmation.
    loadGate.resolve(HttpResponse.json([activeKey]))
    await flushPromises()
    await wrapper.get('[data-test="delete-api-key-31"]').trigger('click')
    wrapper.unmount()
    confirmGate.resolve({} as MessageBoxData)
    await flushPromises()

    expect(deleteCalls).toBe(0)
    expect(document.body.textContent).not.toContain('sk-gw-')
  })
})
