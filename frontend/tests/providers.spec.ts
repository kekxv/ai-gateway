import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessageBox, type MessageBoxData } from 'element-plus'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ProviderResponse } from '@/api/types'
import ProviderFormDrawer from '@/components/providers/ProviderFormDrawer.vue'
import { routes } from '@/router'
import ProvidersView from '@/views/ProvidersView.vue'

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

async function waitForFormErrors(): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, 120))
  await flushPromises()
}

const providerFixture: ProviderResponse = {
  id: 1,
  name: 'OpenAI 主线路',
  has_credential: true,
  enabled: true,
  auto_load_models: true,
  model_sync_interval_seconds: 3600,
  last_model_sync_at: '2026-07-22T08:30:00Z',
  price_multiplier: 1.0,
  protocols: [
    {
      id: 11,
      protocol: 'openai',
      base_url: 'https://api.openai.com/v1',
      websocket_url: null,
      has_extra_headers: true,
      enabled: true,
    },
    {
      id: 12,
      protocol: 'claude',
      base_url: 'https://claude.example.com',
      websocket_url: 'wss://claude.example.com/ws',
      has_extra_headers: false,
      enabled: false,
    },
  ],
}

const geminiFixture: ProviderResponse = {
  ...providerFixture,
  id: 2,
  name: 'Gemini 备用线路',
  auto_load_models: false,
  last_model_sync_at: null,
  protocols: [
    {
      id: 21,
      protocol: 'gemini',
      base_url: 'https://generativelanguage.googleapis.com',
      websocket_url: null,
      has_extra_headers: false,
      enabled: true,
    },
  ],
}

const server = setupServer()

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

beforeEach(() => {
  server.use(
    http.get('/admin/providers/:providerId/discover-models', () =>
      HttpResponse.json({ openai: ['gpt-4.1'] }),
    ),
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

function useProviderList(providers: ProviderResponse[] = [providerFixture]): void {
  server.use(http.get('/admin/providers', () => HttpResponse.json(providers)))
}

async function mountProviders(
  providers: ProviderResponse[] = [providerFixture],
): Promise<VueWrapper> {
  useProviderList(providers)
  const wrapper = mount(ProvidersView, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

async function confirmSelectedModels(wrapper: VueWrapper): Promise<void> {
  await flushPromises()
  const confirmButton = wrapper
    .findAll('button')
    .find((button) => button.text().includes('同步选中的模型'))
  if (confirmButton === undefined) throw new Error('未找到模型同步确认按钮')
  await confirmButton.trigger('click')
  await flushPromises()
}

describe('供应商与协议管理', () => {
  it('通过独立懒加载路由提供供应商页面', async () => {
    const shellRoute = routes.find((route) => route.path === '/')
    const providerRoute = shellRoute?.children?.find((route) => route.name === 'providers')
    if (typeof providerRoute?.component !== 'function') {
      throw new Error('供应商路由不是懒加载组件')
    }

    const loadProviders = providerRoute.component as () => Promise<{ default: unknown }>
    const loadedModule = await loadProviders()
    expect(loadedModule.default).toBe(ProvidersView)
  })

  it('渲染协议状态并按名称、协议或基础地址搜索', async () => {
    const wrapper = await mountProviders([providerFixture, geminiFixture])

    expect(wrapper.text()).toContain('OpenAI 主线路')
    expect(wrapper.text()).toContain('Gemini 备用线路')
    expect(wrapper.text()).toContain('自动同步')
    expect(wrapper.text()).toContain('从未同步')

    await wrapper.get('[data-test="provider-search"]').setValue('claude.example.com')
    expect(wrapper.text()).toContain('OpenAI 主线路')
    expect(wrapper.text()).not.toContain('Gemini 备用线路')

    await wrapper.get('[data-test="provider-search"]').setValue('gemini')
    expect(wrapper.text()).not.toContain('OpenAI 主线路')
    expect(wrapper.text()).toContain('Gemini 备用线路')
    wrapper.unmount()
  })

  it('编辑时只发送变更字段，不发送空白凭据或空白协议请求头', async () => {
    const requests: unknown[] = []
    server.use(
      http.patch('/admin/providers/1', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json({ ...providerFixture, name: 'OpenAI 核心线路' })
      }),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="edit-provider-1"]').trigger('click')
    await flushPromises()
    const drawer = wrapper.getComponent(ProviderFormDrawer)
    await drawer.get('[data-test="provider-name"]').setValue('OpenAI 核心线路')
    await drawer.get('[data-test="provider-credential"]').setValue('   ')
    await drawer.get('[data-test="protocol-extra-headers-0"]').setValue('')
    await drawer.get('[data-test="provider-submit"]').trigger('click')
    await flushPromises()

    expect(requests).toHaveLength(1)
    expect(requests[0]).toEqual({ name: 'OpenAI 核心线路' })
    expect(JSON.stringify(requests[0])).not.toContain('credential')
    expect(JSON.stringify(requests[0])).not.toContain('extra_headers')
    wrapper.unmount()
  })

  it('编辑协议时保留每条协议编号', async () => {
    const requests: unknown[] = []
    server.use(
      http.patch('/admin/providers/1', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json(providerFixture)
      }),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="edit-provider-1"]').trigger('click')
    await flushPromises()
    const drawer = wrapper.getComponent(ProviderFormDrawer)
    await drawer
      .get('[data-test="protocol-base-url-0"]')
      .setValue('https://proxy.example.com/v1')
    await drawer.get('[data-test="provider-submit"]').trigger('click')
    await flushPromises()

    expect(requests[0]).toMatchObject({
      protocols: [
        { id: 11, base_url: 'https://proxy.example.com/v1' },
        { id: 12, base_url: 'https://claude.example.com' },
      ],
    })
    expect(JSON.stringify(requests[0])).not.toContain('extra_headers')
    wrapper.unmount()
  })

  it('创建时支持多条协议，并把高级对象凭据与请求头发送到接口', async () => {
    const requests: unknown[] = []
    useProviderList([])
    server.use(
      http.post('/admin/providers', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json(providerFixture, { status: 201 })
      }),
    )
    const wrapper = mount(ProvidersView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="create-provider"]').trigger('click')
    const drawer = wrapper.getComponent(ProviderFormDrawer)
    await drawer.get('[data-test="provider-name"]').setValue('聚合供应商')
    await drawer.get('[data-test="provider-credential"]').setValue('{"api_key":"secret"}')
    await drawer.get('[data-test="protocol-base-url-0"]').setValue('https://one.example.com')
    await drawer.get('[data-test="protocol-extra-headers-0"]').setValue('{"X-Tenant":"one"}')
    await drawer.get('[data-test="add-protocol"]').trigger('click')
    await drawer.get('[data-test="protocol-type-1"]').setValue('claude')
    await drawer.get('[data-test="protocol-base-url-1"]').setValue('https://two.example.com')
    await drawer.get('[data-test="provider-submit"]').trigger('click')
    await flushPromises()

    expect(requests).toHaveLength(1)
    expect(requests[0]).toMatchObject({
      name: '聚合供应商',
      credential: { api_key: 'secret' },
      protocols: [
        {
          protocol: 'openai',
          base_url: 'https://one.example.com',
          extra_headers: { 'X-Tenant': 'one' },
        },
        { protocol: 'claude', base_url: 'https://two.example.com' },
      ],
    })
    wrapper.unmount()
  })

  it('创建无认证供应商时省略空白凭据', async () => {
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('本地 Ollama')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('http://ollama:11434/v1')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')
    await flushPromises()

    const payload = wrapper.emitted('submit')?.[0]?.[0]
    expect(payload).toEqual({
      name: '本地 Ollama',
      enabled: true,
      auto_load_models: false,
      model_sync_interval_seconds: 3600,
      protocols: [
        {
          protocol: 'openai',
          base_url: 'http://ollama:11434/v1',
          websocket_url: null,
          enabled: true,
        },
      ],
      price_multiplier: 1,
    })
    expect(payload).not.toHaveProperty('credential')
    wrapper.unmount()
  })

  it('合并高级凭据中的任意字段，并让引导字段覆盖保留键', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('高级凭据供应商')
    await wrapper.get('[data-test="provider-api-key"]').setValue('guided-secret')
    await wrapper.get('[data-test="provider-auth-scheme"]').setValue('apikey')
    await wrapper.get('[data-test="provider-auth-header"]').setValue('x-api-key')
    await wrapper
      .get('[data-test="provider-credential"]')
      .setValue('{"tenant":"north","api_key":"advanced-secret","auth_scheme":"ignored","auth_header":"Ignored"}')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('https://api.example.com')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        credential: {
          tenant: 'north',
          api_key: 'guided-secret',
          auth_scheme: 'ApiKey',
          auth_header: 'x-api-key',
        },
      }),
    )
    wrapper.unmount()
  })

  it('分别在凭据字段和协议请求头字段拒绝非对象 JSON', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('无效配置')
    await wrapper.get('[data-test="provider-credential"]').setValue('[]')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('https://api.example.com')
    await wrapper.get('[data-test="protocol-extra-headers-0"]').setValue('"token"')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')
    await waitForFormErrors()

    expect(wrapper.get('[data-validation="credential"] .el-form-item__error').text()).toContain(
      '必须是 JSON 对象',
    )
    expect(wrapper.get('[data-test="protocol-extra-field-0"] .el-form-item__error').text()).toContain(
      '必须是 JSON 对象',
    )
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('拒绝作为高级凭据的 JSON 标量', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('无效配置')
    await wrapper.get('[data-test="provider-credential"]').setValue('"token"')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('https://api.example.com')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')
    await waitForFormErrors()

    expect(wrapper.get('[data-validation="credential"] .el-form-item__error').text()).toContain(
      '必须是 JSON 对象',
    )
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('拒绝格式错误的高级凭据 JSON', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('无效配置')
    await wrapper.get('[data-test="provider-credential"]').setValue('{"api_key":')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('https://api.example.com')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')
    await waitForFormErrors()

    expect(wrapper.get('[data-validation="credential"] .el-form-item__error').text()).toContain(
      'JSON 格式不正确',
    )
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('显示模型同步响应中的全部计数', async () => {
    server.use(
      http.post('/admin/providers/1/sync-models', () =>
        HttpResponse.json({
          provider_id: 1,
          discovered_models: 12,
          created_models: 2,
          created_routes: 3,
          updated_routes: 4,
          disabled_routes: 1,
        }),
      ),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await confirmSelectedModels(wrapper)

    expect(wrapper.get('[data-test="provider-notice"]').text()).toContain(
      '发现 12 个，新增模型 2 个，新增路由 3 条，更新路由 4 条，停用路由 1 条',
    )
    wrapper.unmount()
  })

  it('供应商已有历史记录时保留列表项并引导改为停用', async () => {
    let deleteRequests = 0
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(
      http.post('/admin/providers/1/sync-models', () =>
        HttpResponse.json({
          provider_id: 1,
          discovered_models: 1,
          created_models: 0,
          created_routes: 0,
          updated_routes: 0,
          disabled_routes: 0,
        }),
      ),
      http.delete('/admin/providers/1', () => {
        deleteRequests += 1
        return HttpResponse.json(
          {
            detail: {
              code: 'provider_has_history',
              message: 'Providers with request history must be disabled instead of deleted',
            },
          },
          { status: 409 },
        )
      }),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="delete-provider-1"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('OpenAI 主线路')
    expect(wrapper.get('[data-test="provider-notice"]').text()).toContain('请求历史')
    expect(wrapper.get('[data-test="provider-notice"]').text()).toContain('停用')
    expect(wrapper.get('[data-test="delete-provider-1"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="delete-provider-1"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-test="delete-provider-1"]').trigger('click')
    await flushPromises()
    expect(deleteRequests).toBe(1)
    wrapper.unmount()
  })

  it('提交期间阻止关闭、取消和替换草稿，并让卸载后的响应失效', async () => {
    const patchResponse = deferred<ProviderResponse>()
    server.use(
      http.patch('/admin/providers/1', async () => HttpResponse.json(await patchResponse.promise)),
    )
    const wrapper = await mountProviders([providerFixture, geminiFixture])

    await wrapper.get('[data-test="edit-provider-1"]').trigger('click')
    const drawer = wrapper.getComponent(ProviderFormDrawer)
    await drawer.get('[data-test="provider-name"]').setValue('延迟保存线路')
    await drawer.get('[data-test="provider-credential"]').setValue('{"api_key":"delayed"}')
    await drawer.get('[data-test="provider-submit"]').trigger('click')
    await flushPromises()

    expect(drawer.get('[data-test="provider-cancel"]').attributes('disabled')).toBeDefined()
    expect(drawer.find('.el-drawer__close-btn').exists()).toBe(false)
    await drawer.get('[data-test="provider-cancel"]').trigger('click')
    await wrapper.get('[data-test="create-provider"]').trigger('click')
    expect(drawer.text()).toContain('编辑供应商')
    expect(drawer.get('[data-test="provider-name"]').element).toHaveProperty(
      'value',
      '延迟保存线路',
    )

    wrapper.unmount()
    const replacement = await mountProviders([])
    await replacement.get('[data-test="create-provider"]').trigger('click')
    patchResponse.resolve({ ...providerFixture, name: '延迟保存线路' })
    await flushPromises()

    expect(replacement.getComponent(ProviderFormDrawer).text()).toContain('新建供应商')
    expect(replacement.find('[data-test="provider-notice"]').exists()).toBe(false)
    replacement.unmount()
  })

  it('同一供应商的编辑、同步和删除互斥，并拦截重复同步', async () => {
    const syncResponse = deferred<{
      provider_id: number
      discovered_models: number
      created_models: number
      created_routes: number
      updated_routes: number
      disabled_routes: number
    }>()
    let syncRequests = 0
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(
      http.post('/admin/providers/1/sync-models', async () => {
        syncRequests += 1
        return HttpResponse.json(await syncResponse.promise)
      }),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await confirmSelectedModels(wrapper)
    expect(wrapper.get('[data-test="sync-provider-1"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await wrapper.get('[data-test="edit-provider-1"]').trigger('click')
    await wrapper.get('[data-test="delete-provider-1"]').trigger('click')
    await flushPromises()

    expect(syncRequests).toBe(1)
    expect(confirm).not.toHaveBeenCalled()
    expect(wrapper.findComponent(ProviderFormDrawer).props('modelValue')).toBe(false)
    expect(wrapper.get('[data-test="edit-provider-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="delete-provider-1"]').attributes('disabled')).toBeDefined()

    syncResponse.resolve({
      provider_id: 1,
      discovered_models: 1,
      created_models: 0,
      created_routes: 0,
      updated_routes: 0,
      disabled_routes: 0,
    })
    await flushPromises()

    await wrapper.get('[data-test="edit-provider-1"]').trigger('click')
    expect(wrapper.get('[data-test="sync-provider-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="delete-provider-1"]').attributes('disabled')).toBeDefined()
    await wrapper
      .getComponent(ProviderFormDrawer)
      .get('[data-test="provider-cancel"]')
      .trigger('click')
    wrapper.unmount()
  })

  it('删除确认和请求期间拦截重复点击及其他行操作', async () => {
    const confirmResult = deferred<MessageBoxData>()
    const deleteResponse = deferred<null>()
    let deleteRequests = 0
    let syncRequests = 0
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockReturnValue(confirmResult.promise)
    server.use(
      http.delete('/admin/providers/1', async () => {
        deleteRequests += 1
        await deleteResponse.promise
        return new HttpResponse(null, { status: 204 })
      }),
      http.post('/admin/providers/1/sync-models', () => {
        syncRequests += 1
        return HttpResponse.json({
          provider_id: 1,
          discovered_models: 0,
          created_models: 0,
          created_routes: 0,
          updated_routes: 0,
          disabled_routes: 0,
        })
      }),
    )
    const wrapper = await mountProviders()

    const deleteButton = wrapper.get('[data-test="delete-provider-1"]')
    await Promise.all([deleteButton.trigger('click'), deleteButton.trigger('click')])
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-test="sync-provider-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="edit-provider-1"]').attributes('disabled')).toBeDefined()

    confirmResult.resolve({ value: '', action: 'confirm' } as MessageBoxData)
    await flushPromises()
    await wrapper.get('[data-test="delete-provider-1"]').trigger('click')
    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await wrapper.get('[data-test="edit-provider-1"]').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledTimes(1)
    expect(deleteRequests).toBe(1)
    expect(syncRequests).toBe(0)
    expect(wrapper.findComponent(ProviderFormDrawer).props('modelValue')).toBe(false)

    deleteResponse.resolve(null)
    await flushPromises()
    expect(wrapper.find('[data-test="delete-provider-1"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="provider-notice"]').text()).toContain('已删除')
    wrapper.unmount()
  })

  it('组件卸载后即使删除确认成功也不发送请求或发布消息', async () => {
    const confirmResult = deferred<MessageBoxData>()
    let deleteRequests = 0
    vi.spyOn(ElMessageBox, 'confirm').mockReturnValue(confirmResult.promise)
    server.use(
      http.delete('/admin/providers/1', () => {
        deleteRequests += 1
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="delete-provider-1"]').trigger('click')
    wrapper.unmount()
    confirmResult.resolve({ value: '', action: 'confirm' } as MessageBoxData)
    await flushPromises()

    expect(deleteRequests).toBe(0)
    expect(document.querySelector('[data-test="provider-notice"]')).toBeNull()
    expect(document.body.textContent).not.toContain('已删除')
  })

  it('删除成功后保留本地删除结果，不允许较早的列表响应恢复该行', async () => {
    const staleList = deferred<ProviderResponse[]>()
    let listRequests = 0
    server.use(
      http.get('/admin/providers', async () => {
        listRequests += 1
        if (listRequests === 1) return HttpResponse.json([providerFixture, geminiFixture])
        return HttpResponse.json(await staleList.promise)
      }),
      http.post('/admin/providers/1/sync-models', () =>
        HttpResponse.json({
          provider_id: 1,
          discovered_models: 2,
          created_models: 0,
          created_routes: 0,
          updated_routes: 0,
          disabled_routes: 0,
        }),
      ),
      http.delete('/admin/providers/2', () => new HttpResponse(null, { status: 204 })),
    )
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    const wrapper = mount(ProvidersView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await confirmSelectedModels(wrapper)
    await wrapper.get('[data-test="delete-provider-2"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="delete-provider-2"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="provider-notice"]').text()).toContain('已删除')

    staleList.resolve([providerFixture, geminiFixture])
    await flushPromises()
    expect(wrapper.find('[data-test="delete-provider-2"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('本地删除成功后忽略较早列表的迟到失败并继续显示有效列表', async () => {
    const staleList = deferred<Response>()
    let listRequests = 0
    server.use(
      http.get('/admin/providers', () => {
        listRequests += 1
        if (listRequests === 1) return HttpResponse.json([providerFixture, geminiFixture])
        return staleList.promise
      }),
      http.post('/admin/providers/1/sync-models', () =>
        HttpResponse.json({
          provider_id: 1,
          discovered_models: 2,
          created_models: 0,
          created_routes: 0,
          updated_routes: 0,
          disabled_routes: 0,
        }),
      ),
      http.delete('/admin/providers/2', () => new HttpResponse(null, { status: 204 })),
    )
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    const wrapper = mount(ProvidersView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await confirmSelectedModels(wrapper)
    await wrapper.get('[data-test="delete-provider-2"]').trigger('click')
    await flushPromises()
    staleList.resolve(HttpResponse.json(null, { status: 500 }))
    await flushPromises()

    expect(wrapper.text()).toContain('OpenAI 主线路')
    expect(wrapper.find('[data-test="delete-provider-2"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('供应商列表加载失败')
    wrapper.unmount()
  })

  it('同步间隔必须是大于等于 1 的整数，清空后聚焦该字段且不提交 null', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: providerFixture, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    const intervalInput = wrapper.get('[data-test="provider-sync-interval"] input')
    await intervalInput.setValue('')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')
    await waitForFormErrors()

    expect(wrapper.get('[data-test="sync-interval-field"] .el-form-item__error').text()).toContain(
      '请输入大于等于 1 的整数',
    )
    expect(document.activeElement).toBe(intervalInput.element)
    expect(onSubmit).not.toHaveBeenCalled()

    await intervalInput.setValue('1.5')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')
    await waitForFormErrors()
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('仅显示一份错误，并将第二条协议的行内错误聚焦到对应输入框', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('行内校验')
    await wrapper.get('[data-test="provider-credential"]').setValue('{"api_key":"secret"}')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('https://one.example.com')
    await wrapper.get('[data-test="add-protocol"]').trigger('click')
    await wrapper.get('[data-test="protocol-base-url-1"]').setValue('https://two.example.com')
    const secondHeaders = wrapper.get('[data-test="protocol-extra-headers-1"]')
    await secondHeaders.setValue('[]')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')
    await waitForFormErrors()

    const matchingErrors = wrapper
      .findAll('.el-form-item__error')
      .filter((item) => item.text().includes('必须是 JSON 对象'))
    expect(matchingErrors).toHaveLength(1)
    expect(wrapper.get('[data-test="protocol-extra-field-1"]').text()).toContain(
      '必须是 JSON 对象',
    )
    expect(document.activeElement).toBe(secondHeaders.element)
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('取消时立即清除凭据和额外请求头草稿', async () => {
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false },
      attachTo: document.body,
    })
    await flushPromises()

    const credential = wrapper.get('[data-test="provider-credential"]')
    const headers = wrapper.get('[data-test="protocol-extra-headers-0"]')
    await credential.setValue('{"api_key":"never-retain"}')
    await headers.setValue('{"Authorization":"never-retain"}')
    await wrapper.get('[data-test="provider-cancel"]').trigger('click')
    await flushPromises()

    expect(credential.element).toHaveProperty('value', '')
    expect(headers.element).toHaveProperty('value', '')
    wrapper.unmount()
  })

  it('编辑时发送有效的替换凭据与替换请求头', async () => {
    const requests: unknown[] = []
    server.use(
      http.patch('/admin/providers/1', async ({ request }) => {
        requests.push(await request.json())
        return HttpResponse.json(providerFixture)
      }),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="edit-provider-1"]').trigger('click')
    const drawer = wrapper.getComponent(ProviderFormDrawer)
    const credential = drawer.get('[data-test="provider-credential"]')
    const headers = drawer.get('[data-test="protocol-extra-headers-0"]')
    await credential.setValue('{"api_key":"replacement"}')
    await headers.setValue('{"Authorization":"replacement"}')
    await drawer.get('[data-test="provider-submit"]').trigger('click')
    await flushPromises()

    expect(requests[0]).toMatchObject({
      credential: { api_key: 'replacement' },
      protocols: [
        { id: 11, extra_headers: { Authorization: 'replacement' } },
        { id: 12 },
      ],
    })
    expect(credential.element).toHaveProperty('value', '')
    expect(headers.element).toHaveProperty('value', '')
    wrapper.unmount()
  })

  it('创建和编辑都允许删除最后一条协议并提交空列表', async () => {
    const createSubmit = vi.fn()
    const createDrawer = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit: createSubmit },
      attachTo: document.body,
    })
    await flushPromises()
    await createDrawer.get('[data-test="provider-name"]').setValue('无协议供应商')
    await createDrawer.get('[data-test="provider-credential"]').setValue('{"api_key":"secret"}')
    await createDrawer.get('[data-test="remove-protocol-0"]').trigger('click')
    await createDrawer.get('[data-test="provider-submit"]').trigger('click')
    await flushPromises()
    expect(createSubmit).toHaveBeenCalledWith(expect.objectContaining({ protocols: [] }))
    createDrawer.unmount()

    const editSubmit = vi.fn()
    const firstProtocol = providerFixture.protocols[0]
    if (firstProtocol === undefined) throw new Error('测试供应商缺少协议')
    const oneProtocolProvider = { ...providerFixture, protocols: [firstProtocol] }
    const editDrawer = mount(ProviderFormDrawer, {
      props: {
        modelValue: true,
        provider: oneProtocolProvider,
        submitting: false,
        onSubmit: editSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()
    await editDrawer.get('[data-test="remove-protocol-0"]').trigger('click')
    await editDrawer.get('[data-test="provider-submit"]').trigger('click')
    await flushPromises()
    expect(editSubmit).toHaveBeenCalledWith({ protocols: [] })
    editDrawer.unmount()
  })
})
