import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessageBox, type MessageBoxData } from 'element-plus'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ModelResponse, ProviderResponse } from '@/api/types'
import ProviderFormDrawer from '@/components/providers/ProviderFormDrawer.vue'
import ModelSyncDialog from '@/components/providers/ModelSyncDialog.vue'
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
  proxy: { mode: 'inherit', url: null, auth_type: null, has_auth: false },
  enabled: true,
  auto_load_models: true,
  model_sync_interval_seconds: 3600,
  last_model_sync_at: '2026-07-22T08:30:00Z',
  cost_multiplier: 1.0,
  public_multiplier: 1.0,
  protocols: [
    {
      id: 11,
      protocol: 'openai',
      base_url: 'https://api.openai.com/v1',
      websocket_url: null,
      has_extra_headers: true,
      supports_responses: true,
      enabled: true,
    },
    {
      id: 12,
      protocol: 'claude',
      base_url: 'https://claude.example.com',
      websocket_url: 'wss://claude.example.com/ws',
      has_extra_headers: false,
      supports_responses: true,
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
      supports_responses: true,
      enabled: true,
    },
  ],
}

const harnessModelsFixture: ModelResponse[] = [
  {
    id: 101,
    canonical_name: 'chat-model',
    display_name: 'Chat model',
    model_type: 'text',
    input_price_per_million: '0',
    output_price_per_million: '0',
    cache_read_price_per_million: '0',
    cache_write_price_per_million: '0',
    price_multiplier: 1,
    enabled: true,
    aliases: [],
    routing_strategy: 'weighted_random',
    created_at: '2026-08-14T00:00:00Z',
    updated_at: '2026-08-14T00:00:00Z',
  },
  {
    id: 102,
    canonical_name: 'vision-model',
    display_name: 'Vision model',
    model_types: ['text', 'image'],
    input_price_per_million: '0',
    output_price_per_million: '0',
    cache_read_price_per_million: '0',
    cache_write_price_per_million: '0',
    price_multiplier: 1,
    enabled: true,
    aliases: [],
    routing_strategy: 'weighted_random',
    created_at: '2026-08-14T00:00:00Z',
    updated_at: '2026-08-14T00:00:00Z',
  },
  {
    id: 103,
    canonical_name: 'disabled-model',
    display_name: 'Disabled model',
    model_type: 'text',
    input_price_per_million: '0',
    output_price_per_million: '0',
    cache_read_price_per_million: '0',
    cache_write_price_per_million: '0',
    price_multiplier: 1,
    enabled: false,
    aliases: [],
    routing_strategy: 'weighted_random',
    created_at: '2026-08-14T00:00:00Z',
    updated_at: '2026-08-14T00:00:00Z',
  },
]

const server = setupServer()

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

beforeEach(() => {
  server.use(
    http.get('/admin/providers/:providerId/discover-models', () =>
      HttpResponse.json({ openai: ['gpt-4.1'] }),
    ),
    http.get('/admin/providers/:providerId', ({ params }) =>
      HttpResponse.json(Number(params.providerId) === 2 ? geminiFixture : providerFixture),
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

async function mountProvidersView(): Promise<VueWrapper> {
  const wrapper = mount(ProvidersView, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

async function mountProviders(
  providers: ProviderResponse[] = [providerFixture],
): Promise<VueWrapper> {
  useProviderList(providers)
  return mountProvidersView()
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
  it('生成 DeepSeek Harness 配置时仅导出启用模型', async () => {
    server.use(http.get('/admin/models', () => HttpResponse.json(harnessModelsFixture)))
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="generate-deepseek-harness-config"]').trigger('click')
    await flushPromises()

    const settings = wrapper.get('[data-test="deepseek-harness-settings"]').text()
    expect(settings).toContain('api: openai-responses')
    expect(settings).toContain('id: chat-model')
    expect(settings).toContain('id: vision-model')
    expect(settings).toContain('input: [text, image]')
    expect(settings).not.toContain('disabled-model')
    wrapper.unmount()
  })

  it('重新加载 Harness 模型时清除过期默认模型并禁用导出', async () => {
    const reloadedModels = deferred<Response>()
    let modelRequests = 0
    server.use(http.get('/admin/models', () => {
      modelRequests += 1
      return modelRequests === 1 ? HttpResponse.json(harnessModelsFixture) : reloadedModels.promise
    }))
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="generate-deepseek-harness-config"]').trigger('click')
    await flushPromises()
    await wrapper.get('#harness-default-model').setValue('chat-model')
    await wrapper.get('[data-test="deepseek-harness-close"]').trigger('click')
    await wrapper.get('[data-test="generate-deepseek-harness-config"]').trigger('click')
    await wrapper.get('[data-test="deepseek-harness-api-key"]').setValue('sk-gw-secret')

    expect(wrapper.get<HTMLSelectElement>('#harness-default-model').element.value).toBe('')
    expect(wrapper.get('[data-test="deepseek-harness-download-settings"]').attributes('aria-disabled')).toBe('true')

    reloadedModels.resolve(HttpResponse.json([
      { ...harnessModelsFixture[0], enabled: false },
      harnessModelsFixture[1],
    ]))
    await flushPromises()

    expect(wrapper.get<HTMLSelectElement>('#harness-default-model').element.value).toBe('')
    expect(wrapper.get('[data-test="deepseek-harness-download-settings"]').attributes('aria-disabled')).toBe('true')
    wrapper.unmount()
  })

  it('忽略过期 Harness 模型加载响应', async () => {
    const staleResponse = deferred<Response>()
    const currentResponse = deferred<Response>()
    let modelRequests = 0
    server.use(http.get('/admin/models', () => {
      modelRequests += 1
      if (modelRequests === 1) return HttpResponse.json(harnessModelsFixture)
      return modelRequests === 2 ? staleResponse.promise : currentResponse.promise
    }))
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="generate-deepseek-harness-config"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="deepseek-harness-close"]').trigger('click')
    await wrapper.get('[data-test="generate-deepseek-harness-config"]').trigger('click')
    await wrapper.get('[data-test="generate-deepseek-harness-config"]').trigger('click')
    currentResponse.resolve(HttpResponse.json([harnessModelsFixture[1]]))
    await flushPromises()
    staleResponse.resolve(HttpResponse.json([harnessModelsFixture[0]]))
    await flushPromises()

    const optionValues = wrapper.findAll('#harness-default-model option').map((option) => option.attributes('value'))
    expect(optionValues).toContain('vision-model')
    expect(optionValues).not.toContain('chat-model')
    wrapper.unmount()
  })

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

  it('将启用与停用供应商分区并显示各自数量', async () => {
    const disabledProvider = { ...geminiFixture, enabled: false }
    const wrapper = await mountProviders([providerFixture, disabledProvider])

    const enabledGroup = wrapper.get('[data-test="enabled-provider-group"]')
    const disabledGroup = wrapper.get('[data-test="disabled-provider-group"]')
    expect(enabledGroup.text()).toContain('启用中')
    expect(enabledGroup.text()).toContain('1 个')
    expect(enabledGroup.find('[data-test="provider-card-1"]').exists()).toBe(true)
    expect(enabledGroup.find('[data-test="provider-card-2"]').exists()).toBe(false)
    expect(disabledGroup.text()).toContain('已停用')
    expect(disabledGroup.text()).toContain('1 个')
    expect(disabledGroup.find('[data-test="provider-card-2"]').exists()).toBe(true)
    expect(disabledGroup.find('[data-test="provider-card-1"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('通过快捷操作启用供应商并将它移入启用分区', async () => {
    const patchBodies: unknown[] = []
    const disabledProvider = { ...providerFixture, enabled: false }
    server.use(
      http.patch('/admin/providers/1', async ({ request }) => {
        patchBodies.push(await request.json())
        return HttpResponse.json({ ...providerFixture, enabled: true })
      }),
    )
    const wrapper = await mountProviders([disabledProvider])

    await wrapper.get('[data-test="toggle-provider-1"]').trigger('click')
    await flushPromises()

    expect(patchBodies).toEqual([{ enabled: true }])
    expect(wrapper.get('[data-test="enabled-provider-group"]').find('[data-test="provider-card-1"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('将供应商操作按钮置于标题下方的独立一行', async () => {
    const wrapper = await mountProviders()

    const card = wrapper.get('[data-test="provider-card-1"]')
    expect(card.find('.card-header .card-actions').exists()).toBe(false)
    expect(card.find('.card-header + .card-actions').exists()).toBe(true)
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

  it('OpenAI 协议可显式关闭 Responses 原生支持', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('旧版 OpenAI 后端')
    await wrapper
      .get('[data-test="protocol-base-url-0"]')
      .setValue('https://legacy-openai.example/v1')
    await wrapper
      .get('[data-test="protocol-supports-responses-0"] input')
      .setValue(false)
    await wrapper.get('[data-test="provider-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        protocols: [
          expect.objectContaining({
            protocol: 'openai',
            supports_responses: false,
          }),
        ],
      }),
    )
    wrapper.unmount()
  })

  it('非 OpenAI 协议始终归一化为支持 Responses', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('Claude 后端')
    await wrapper.get('[data-test="protocol-type-0"]').setValue('claude')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('https://claude.example.com')
    expect(wrapper.find('[data-test="protocol-supports-responses-0"]').exists()).toBe(false)
    await wrapper.get('[data-test="provider-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        protocols: [expect.objectContaining({ protocol: 'claude', supports_responses: true })],
      }),
    )
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
          supports_responses: true,
          enabled: true,
        },
      ],
      cost_multiplier: 1,
      public_multiplier: 1,
    })
    expect(payload).not.toHaveProperty('credential')
    wrapper.unmount()
  })

  it('创建供应商时提交带用户名密码的专用代理', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('代理供应商')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('https://api.example.com/v1')
    await wrapper.get('[data-test="provider-proxy-mode"]').setValue('custom')
    await wrapper.get('[data-test="provider-proxy-url"]').setValue('http://proxy.internal:8080')
    await wrapper.get('[data-test="provider-proxy-auth-type"]').setValue('basic')
    await wrapper.get('[data-test="provider-proxy-username"]').setValue('proxy-user')
    await wrapper.get('[data-test="provider-proxy-password"]').setValue('proxy-password')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        proxy: {
          mode: 'custom',
          url: 'http://proxy.internal:8080',
          auth: { type: 'basic', username: 'proxy-user', password: 'proxy-password' },
        },
      }),
    )
    wrapper.unmount()
  })

  it('编辑供应商切换为继承全局代理时提交 null', async () => {
    const onSubmit = vi.fn()
    const proxiedProvider: ProviderResponse = {
      ...providerFixture,
      proxy: {
        mode: 'custom',
        url: 'http://proxy.internal:8080',
        auth_type: 'basic',
        has_auth: true,
      },
    }
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: proxiedProvider, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-proxy-mode"]').setValue('inherit')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({ proxy: null })
    wrapper.unmount()
  })

  it('自定义代理鉴权请求头不允许与 WebSocket 入口同时提交', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('实时代理供应商')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('https://api.example.com/v1')
    await wrapper.get('[data-test="protocol-websocket-url-0"]').setValue('wss://api.example.com/ws')
    await wrapper.get('[data-test="provider-proxy-mode"]').setValue('custom')
    await wrapper.get('[data-test="provider-proxy-url"]').setValue('http://proxy.internal:8080')
    await wrapper.get('[data-test="provider-proxy-auth-type"]').setValue('headers')
    await wrapper
      .get('[data-test="provider-proxy-headers"]')
      .setValue('{"Proxy-Authorization":"Bearer secret"}')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')
    await waitForFormErrors()

    expect(onSubmit).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('WebSocket')
    wrapper.unmount()
  })

  it('混合协议供应商未触碰授权控件时保留各协议默认授权', async () => {
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('混合协议供应商')
    await wrapper.get('[data-test="provider-api-key"]').setValue('mixed-secret')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('https://openai.example.com')
    await wrapper.get('[data-test="add-protocol"]').trigger('click')
    await wrapper.get('[data-test="protocol-type-1"]').setValue('claude')
    await wrapper.get('[data-test="protocol-base-url-1"]').setValue('https://claude.example.com')
    await wrapper.get('[data-test="add-protocol"]').trigger('click')
    await wrapper.get('[data-test="protocol-type-2"]').setValue('gemini')
    await wrapper.get('[data-test="protocol-base-url-2"]').setValue('https://gemini.example.com')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')

    const payload = wrapper.emitted('submit')?.[0]?.[0]
    expect(payload).toMatchObject({
      credential: { api_key: 'mixed-secret' },
      protocols: [
        { protocol: 'openai', base_url: 'https://openai.example.com' },
        { protocol: 'claude', base_url: 'https://claude.example.com' },
        { protocol: 'gemini', base_url: 'https://gemini.example.com' },
      ],
    })
    expect(payload).toHaveProperty('credential', { api_key: 'mixed-secret' })
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

  it('选择无授权时把明确的 none 与 API 密钥一起提交且不提交授权头', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('本地受保护 Ollama')
    await wrapper.get('[data-test="provider-api-key"]').setValue('locally-unused-secret')
    await wrapper.get('[data-test="provider-auth-scheme"]').setValue('none')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('http://ollama:11434/v1')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        credential: {
          api_key: 'locally-unused-secret',
          auth_scheme: 'none',
        },
      }),
    )
    wrapper.unmount()
  })

  it('拒绝不安全的自定义授权头名称', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="provider-name"]').setValue('无效授权头')
    await wrapper.get('[data-test="provider-api-key"]').setValue('secret')
    await wrapper.get('[data-test="provider-auth-header"]').setValue('custom')
    await wrapper.get('[data-test="provider-custom-header"]').setValue('Bad Header')
    await wrapper.get('[data-test="protocol-base-url-0"]').setValue('https://api.example.com')
    await wrapper.get('[data-test="provider-submit"]').trigger('click')
    await waitForFormErrors()

    expect(onSubmit).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('授权头名称格式不正确')
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

  it('在模型同步对话框显示经过后端处理的上游错误', async () => {
    server.use(
      http.get('/admin/providers/1/discover-models', () =>
        HttpResponse.json(
          {
            detail: {
              code: 'model_discovery_failed',
              message: 'Upstream provider returned 401 Unauthorized: Incorrect API key',
            },
          },
          { status: 502 },
        ),
      ),
    )
    const wrapper = mount(ModelSyncDialog, {
      props: {
        modelValue: true,
        providerId: 1,
        providerName: '错误线路',
        submitting: false,
      },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.text()).toContain(
      'Upstream provider returned 401 Unauthorized: Incorrect API key',
    )
    wrapper.unmount()
  })

  it('筛选发现的模型时保留被隐藏模型的已选状态', async () => {
    server.use(
      http.get('/admin/providers/1/discover-models', () =>
        HttpResponse.json({
          openai: ['gpt-4.1'],
          claude: ['claude-sonnet', 'claude-haiku'],
        }),
      ),
    )
    const wrapper = mount(ModelSyncDialog, {
      props: {
        modelValue: true,
        providerId: 1,
        providerName: '筛选线路',
        submitting: false,
      },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="model-sync-filter"]').setValue('claude')

    expect(wrapper.text()).toContain('claude-sonnet')
    expect(wrapper.text()).toContain('claude-haiku')
    expect(wrapper.text()).not.toContain('gpt-4.1')
    expect(wrapper.text()).toContain('同步选中的模型 (3)')
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

  it('编辑供应商时拒绝响应中的其他供应商编号且不改写列表', async () => {
    server.use(
      http.patch('/admin/providers/1', () =>
        HttpResponse.json({ ...geminiFixture, name: '错误注入线路' }),
      ),
    )
    const wrapper = await mountProviders([providerFixture, geminiFixture])

    await wrapper.get('[data-test="edit-provider-1"]').trigger('click')
    const drawer = wrapper.getComponent(ProviderFormDrawer)
    await drawer.get('[data-test="provider-name"]').setValue('OpenAI 修改线路')
    await drawer.get('[data-test="provider-submit"]').trigger('click')
    await flushPromises()

    expect(drawer.props('modelValue')).toBe(true)
    expect(wrapper.get('[data-test="provider-notice"]').text()).toContain('响应供应商不匹配')
    expect(wrapper.get('[data-test="provider-card-1"]').text()).toContain('OpenAI 主线路')
    expect(wrapper.get('[data-test="provider-card-2"]').text()).toContain('Gemini 备用线路')
    expect(wrapper.text()).not.toContain('错误注入线路')
    wrapper.unmount()
  })

  it('同步确认被快速点击两次时只发送一个 POST', async () => {
    const syncResponse = deferred<{
      provider_id: number
      discovered_models: number
      created_models: number
      created_routes: number
      updated_routes: number
      disabled_routes: number
    }>()
    let syncRequests = 0
    server.use(
      http.post('/admin/providers/1/sync-models', async () => {
        syncRequests += 1
        return HttpResponse.json(await syncResponse.promise)
      }),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await flushPromises()
    const confirmButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('同步选中的模型'))
    if (confirmButton === undefined) throw new Error('未找到模型同步确认按钮')
    await Promise.all([confirmButton.trigger('click'), confirmButton.trigger('click')])
    await flushPromises()
    const requestCountWhilePending = syncRequests
    const pendingConfirmButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('同步选中的模型'))
    if (pendingConfirmButton === undefined) throw new Error('模型同步确认按钮提前消失')
    const confirmDisabledWhilePending = pendingConfirmButton.attributes('disabled')

    syncResponse.resolve({
      provider_id: 1,
      discovered_models: 1,
      created_models: 0,
      created_routes: 0,
      updated_routes: 0,
      disabled_routes: 0,
    })
    await flushPromises()

    expect(requestCountWhilePending).toBe(1)
    expect(confirmDisabledWhilePending).toBeDefined()
    wrapper.unmount()
  })

  it('同步 POST 期间取消按钮不能关闭对话框或释放供应商锁', async () => {
    const syncResponse = deferred<{
      provider_id: number
      discovered_models: number
      created_models: number
      created_routes: number
      updated_routes: number
      disabled_routes: number
    }>()
    server.use(
      http.post('/admin/providers/1/sync-models', async () =>
        HttpResponse.json(await syncResponse.promise),
      ),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await confirmSelectedModels(wrapper)
    const cancelButton = wrapper
      .getComponent(ModelSyncDialog)
      .findAll('button')
      .find((button) => button.text() === '取消')
    if (cancelButton === undefined) throw new Error('未找到模型同步取消按钮')
    const cancelDisabledWhilePending = cancelButton.attributes('disabled')
    const closeButtonWhilePending = wrapper
      .getComponent(ModelSyncDialog)
      .find('.el-dialog__headerbtn')
      .exists()
    await cancelButton.trigger('click')
    await flushPromises()
    const dialogStayedOpen = wrapper.getComponent(ModelSyncDialog).props('modelValue')
    const providerStayedLocked = wrapper
      .get('[data-test="edit-provider-1"]')
      .attributes('disabled')

    syncResponse.resolve({
      provider_id: 1,
      discovered_models: 1,
      created_models: 0,
      created_routes: 0,
      updated_routes: 0,
      disabled_routes: 0,
    })
    await flushPromises()

    expect(cancelDisabledWhilePending).toBeDefined()
    expect(closeButtonWhilePending).toBe(false)
    expect(dialogStayedOpen).toBe(true)
    expect(providerStayedLocked).toBeDefined()
    wrapper.unmount()
  })

  it('供应商 A 同步 POST 期间不能用供应商 B 替换对话框目标', async () => {
    const syncResponse = deferred<{
      provider_id: number
      discovered_models: number
      created_models: number
      created_routes: number
      updated_routes: number
      disabled_routes: number
    }>()
    server.use(
      http.post('/admin/providers/1/sync-models', async () =>
        HttpResponse.json(await syncResponse.promise),
      ),
    )
    const wrapper = await mountProviders([providerFixture, geminiFixture])

    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await confirmSelectedModels(wrapper)
    await wrapper.get('[data-test="sync-provider-2"]').trigger('click')
    await flushPromises()
    const targetWhilePending = wrapper.getComponent(ModelSyncDialog).props('providerName')
    const secondProviderLockWhilePending = wrapper
      .get('[data-test="sync-provider-2"]')
      .attributes('disabled')

    syncResponse.resolve({
      provider_id: 1,
      discovered_models: 1,
      created_models: 0,
      created_routes: 0,
      updated_routes: 0,
      disabled_routes: 0,
    })
    await flushPromises()
    const secondProviderLockAfterSync = wrapper
      .get('[data-test="sync-provider-2"]')
      .attributes('disabled')

    expect(targetWhilePending).toBe('OpenAI 主线路')
    expect(secondProviderLockWhilePending).toBeUndefined()
    expect(secondProviderLockAfterSync).toBeUndefined()
    wrapper.unmount()
  })

  it('同步响应供应商编号不匹配时显示错误且不刷新记录', async () => {
    let detailRequests = 0
    server.use(
      http.post('/admin/providers/1/sync-models', () =>
        HttpResponse.json({
          provider_id: 2,
          discovered_models: 1,
          created_models: 0,
          created_routes: 0,
          updated_routes: 0,
          disabled_routes: 0,
        }),
      ),
      http.get('/admin/providers/1', () => {
        detailRequests += 1
        return HttpResponse.json(providerFixture)
      }),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await confirmSelectedModels(wrapper)

    expect(wrapper.get('[data-test="provider-notice"]').text()).toContain('响应供应商不匹配')
    expect(wrapper.get('[data-test="provider-notice"]').text()).not.toContain('同步完成')
    expect(detailRequests).toBe(0)
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

  it('同步 A 的记录刷新与删除 B 独立合并', async () => {
    const refreshReady = deferred<null>()
    const refreshedProvider = {
      ...providerFixture,
      last_model_sync_at: '2031-11-19T09:45:00Z',
    }
    let listRequests = 0
    server.use(
      http.get('/admin/providers', async () => {
        listRequests += 1
        if (listRequests === 1) return HttpResponse.json([providerFixture, geminiFixture])
        await refreshReady.promise
        return HttpResponse.json([refreshedProvider, geminiFixture])
      }),
      http.get('/admin/providers/1', async () => {
        await refreshReady.promise
        return HttpResponse.json(refreshedProvider)
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
    const wrapper = await mountProvidersView()

    await wrapper.get('[data-test="sync-provider-1"]').trigger('click')
    await confirmSelectedModels(wrapper)
    await wrapper.get('[data-test="delete-provider-2"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="delete-provider-2"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="provider-notice"]').text()).toContain('已删除')

    refreshReady.resolve(null)
    await flushPromises()
    expect(wrapper.find('[data-test="delete-provider-2"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="provider-card-1"]').text()).toContain('2031')
    expect(wrapper.get('[data-test="provider-card-1"]').text()).not.toContain('2026')
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

  it('取消时立即清除凭据、代理密码和请求头草稿', async () => {
    const wrapper = mount(ProviderFormDrawer, {
      props: { modelValue: true, provider: null, submitting: false },
      attachTo: document.body,
    })
    await flushPromises()

    const credential = wrapper.get('[data-test="provider-credential"]')
    const headers = wrapper.get('[data-test="protocol-extra-headers-0"]')
    await wrapper.get('[data-test="provider-proxy-mode"]').setValue('custom')
    await wrapper.get('[data-test="provider-proxy-auth-type"]').setValue('basic')
    const proxyUsername = wrapper.get('[data-test="provider-proxy-username"]')
    const proxyPassword = wrapper.get('[data-test="provider-proxy-password"]')
    await credential.setValue('{"api_key":"never-retain"}')
    await headers.setValue('{"Authorization":"never-retain"}')
    await proxyUsername.setValue('never-retain-user')
    await proxyPassword.setValue('never-retain-password')
    await wrapper.get('[data-test="provider-cancel"]').trigger('click')
    await flushPromises()

    expect(credential.element).toHaveProperty('value', '')
    expect(headers.element).toHaveProperty('value', '')
    expect(proxyUsername.element).toHaveProperty('value', '')
    expect(proxyPassword.element).toHaveProperty('value', '')
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

  it('确认后导出包含上游密钥的目录备份并立即撤销下载 URL', async () => {
    let exportRequests = 0
    const createObjectURL = vi.fn().mockReturnValue('blob:catalog-backup')
    const revokeObjectURL = vi.fn()
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(
      http.get('/admin/configuration/export', ({ request }) => {
        exportRequests += 1
        expect(new URL(request.url).searchParams.get('include_secrets')).toBe('true')
        return HttpResponse.json({ format: 'ai-gateway.catalog', version: 1 })
      }),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="export-catalog"]').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('上游 API 密钥'),
      expect.any(String),
      expect.objectContaining({ type: 'warning' }),
    )
    expect(exportRequests).toBe(1)
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(anchorClick).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:catalog-backup')
    const anchor = document.querySelector('a[download="ai-gateway-catalog-v1.json"]')
    expect(anchor).toBeNull()
    wrapper.unmount()
  })

  it('取消目录导出确认时不发送备份请求', async () => {
    let exportRequests = 0
    vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue(new Error('cancel'))
    server.use(
      http.get('/admin/configuration/export', () => {
        exportRequests += 1
        return HttpResponse.json({})
      }),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="export-catalog"]').trigger('click')
    await flushPromises()

    expect(exportRequests).toBe(0)
    wrapper.unmount()
  })

  it('确认后合并 JSON 目录、刷新供应商并显示所有创建和更新计数', async () => {
    const importedCatalog = {
      format: 'ai-gateway.catalog',
      version: 1,
      providers: [{ name: 'Imported provider', protocols: [] }],
      models: [],
    }
    const receivedBundles: unknown[] = []
    let providerListRequests = 0
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(
      http.get('/admin/providers', () => {
        providerListRequests += 1
        return HttpResponse.json(providerListRequests === 1 ? [providerFixture] : [geminiFixture])
      }),
      http.post('/admin/configuration/import', async ({ request }) => {
        receivedBundles.push(await request.json())
        return HttpResponse.json({
          providers_created: 1,
          providers_updated: 2,
          models_created: 3,
          models_updated: 4,
          routes_created: 5,
          routes_updated: 6,
        })
      }),
    )
    const wrapper = await mountProvidersView()
    const file = new File([JSON.stringify(importedCatalog)], 'catalog.json', {
      type: 'application/json',
    })
    const input = wrapper.get<HTMLInputElement>('[data-test="import-catalog-input"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })

    await input.trigger('change')
    await vi.waitFor(() => {
      expect(receivedBundles).toEqual([importedCatalog])
    })

    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('合并'),
      expect.any(String),
      expect.objectContaining({ type: 'warning' }),
    )
    expect(receivedBundles).toEqual([importedCatalog])
    expect(providerListRequests).toBe(2)
    expect(wrapper.text()).toContain('新增供应商 1 个，更新供应商 2 个')
    expect(wrapper.text()).toContain('新增模型 3 个，更新模型 4 个')
    expect(wrapper.text()).toContain('新增路由 5 条，更新路由 6 条')
    expect((input.element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })

  it('以认证 JSON 请求原样发送目录文本并保留最大价格精度', async () => {
    const catalogText =
      '{"format":"ai-gateway.catalog","version":1,"providers":[],"models":[{"canonical_name":"precision-model","display_name":"Precision model","input_price_per_million":999999999999.12345678}]}'
    let receivedBody = ''
    let receivedAuthorization: string | null = null
    let receivedContentType: string | null = null
    localStorage.setItem('gateway.access_token', 'catalog-access-token')
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(
      http.post('/admin/configuration/import', async ({ request }) => {
        receivedBody = await request.text()
        receivedAuthorization = request.headers.get('authorization')
        receivedContentType = request.headers.get('content-type')
        return HttpResponse.json({
          providers_created: 0,
          providers_updated: 0,
          models_created: 1,
          models_updated: 0,
          routes_created: 0,
          routes_updated: 0,
        })
      }),
    )
    const wrapper = await mountProviders()
    const file = new File([catalogText], 'precision-catalog.json', {
      type: 'application/json',
    })
    const input = wrapper.get<HTMLInputElement>('[data-test="import-catalog-input"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })

    await input.trigger('change')
    await vi.waitFor(() => {
      expect(receivedBody).toBe(catalogText)
    })

    expect(receivedBody).toBe(catalogText)
    expect(receivedBody).toContain('999999999999.12345678')
    expect(receivedAuthorization).toBe('Bearer catalog-access-token')
    expect(receivedContentType).toBe('application/json')
    wrapper.unmount()
  })

  it('本地目录 JSON 无效时显示错误且不发送导入请求', async () => {
    let importRequests = 0
    const confirm = vi.spyOn(ElMessageBox, 'confirm')
    server.use(
      http.post('/admin/configuration/import', () => {
        importRequests += 1
        return HttpResponse.json({})
      }),
    )
    const wrapper = await mountProviders()
    const file = new File(['{"format":'], 'broken-catalog.json', { type: 'application/json' })
    const input = wrapper.get<HTMLInputElement>('[data-test="import-catalog-input"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })

    await input.trigger('change')
    await vi.waitFor(() => {
      expect(wrapper.get('[data-test="provider-notice"]').text()).toContain('JSON 格式不正确')
    })

    expect(importRequests).toBe(0)
    expect(confirm).not.toHaveBeenCalled()
    expect((input.element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })
})
