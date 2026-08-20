import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessageBox, type MessageBoxData } from 'element-plus'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createPinia, setActivePinia } from 'pinia'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { listModelRoutes } from '@/api/models'
import type { CurrentUser, ModelResponse, ModelRouteResponse, ProviderResponse } from '@/api/types'
import RouteFormDrawer from '@/components/models/RouteFormDrawer.vue'
import { useAuthStore } from '@/stores/auth'
import ModelsView from '@/views/ModelsView.vue'

async function waitForFormErrors(): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, 120))
  await flushPromises()
}

const models: ModelResponse[] = [
  {
    id: 1,
    canonical_name: 'gpt-4.1',
    display_name: 'GPT 4.1',
    input_price_per_million: '2.00000000',
    output_price_per_million: '8.00000000',
    cache_read_price_per_million: '0.00000000',
    cache_write_price_per_million: '0.00000000',
    price_multiplier: 1.0,
    enabled: true,
    aliases: [{ id: 101, alias: 'fast-chat', enabled: true }],
    routing_strategy: 'weighted_random',
    created_at: '2026-07-22T08:00:00Z',
    updated_at: '2026-07-22T08:00:00Z',
  },
  {
    id: 2,
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
    created_at: '2026-07-22T08:00:00Z',
    updated_at: '2026-07-22T08:00:00Z',
  },
]

const providers: ProviderResponse[] = [
  {
    id: 11,
    name: '多协议主线路',
    has_credential: true,
    proxy: { mode: 'inherit', url: null, auth_type: null, has_auth: false },
    enabled: true,
    auto_load_models: false,
    model_sync_interval_seconds: 3600,
    last_model_sync_at: null,
    cost_multiplier: 1.0,
    public_multiplier: 1.0,
    protocols: [
      {
        id: 111,
        protocol: 'openai',
        base_url: 'https://openai.example.com/v1',
        websocket_url: null,
        has_extra_headers: false,
        supports_responses: true,
        enabled: true,
      },
      {
        id: 112,
        protocol: 'claude',
        base_url: 'https://claude.example.com',
        websocket_url: null,
        has_extra_headers: false,
        supports_responses: true,
        enabled: true,
      },
    ],
  },
  {
    id: 12,
    name: 'Gemini 备用线路',
    has_credential: true,
    proxy: { mode: 'inherit', url: null, auth_type: null, has_auth: false },
    enabled: true,
    auto_load_models: false,
    model_sync_interval_seconds: 3600,
    last_model_sync_at: null,
    cost_multiplier: 1.0,
    public_multiplier: 1.0,
    protocols: [
      {
        id: 121,
        protocol: 'gemini',
        base_url: 'https://gemini.example.com',
        websocket_url: null,
        has_extra_headers: false,
        supports_responses: true,
        enabled: true,
      },
    ],
  },
]

const routeFixture: ModelRouteResponse = {
  id: 201,
  model_id: 1,
  provider_id: 11,
  upstream_model: 'gpt-4.1-2026-04-14',
  weight: 750,
  enabled: true,
  source: 'discovered',
  runtime_state: 'half_open',
  consecutive_failures: 3,
  disabled_until: '2026-07-22T09:15:00Z',
  last_error_code: 'upstream_timeout',
  last_error_at: '2026-07-22T09:00:00Z',
}

const closedRoute: ModelRouteResponse = {
  ...routeFixture,
  id: 202,
  provider_id: 12,
  upstream_model: 'gemini-2.5-pro',
  source: 'manual',
  runtime_state: 'closed',
  consecutive_failures: 0,
  disabled_until: null,
  last_error_code: null,
  last_error_at: null,
}

const openRoute: ModelRouteResponse = {
  ...routeFixture,
  id: 203,
  model_id: 2,
  upstream_model: 'claude-opus-4-1',
  runtime_state: 'open',
}

const adminUser: CurrentUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin',
  is_active: true,
  totp_enabled: false,
  created_at: '2026-07-22T00:00:00Z',
  updated_at: '2026-07-22T00:00:00Z',
}

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

const server = setupServer()

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

beforeEach(() => {
  setActivePinia(createPinia())
  useAuthStore().user = adminUser
})

afterEach(() => {
  vi.restoreAllMocks()
  server.resetHandlers()
  document.body.innerHTML = ''
})

afterAll(() => {
  server.close()
})

function useCatalog(
  onRouteList?: (url: URL) => ModelRouteResponse[],
  providerList: ProviderResponse[] = providers,
): void {
  server.use(
    http.get('/admin/models', () => HttpResponse.json(models)),
    http.get('/admin/providers', () => HttpResponse.json(providerList)),
    http.get('/admin/model-routes', ({ request }) => {
      const url = new URL(request.url)
      if (onRouteList !== undefined) return HttpResponse.json(onRouteList(url))
      const allRoutes = [routeFixture, closedRoute, openRoute]
      const modelId = url.searchParams.get('model_id')
      return HttpResponse.json(
        modelId === null
          ? allRoutes
          : allRoutes.filter((route) => route.model_id === Number(modelId)),
      )
    }),
  )
}

async function mountRoutes(
  onRouteList?: (url: URL) => ModelRouteResponse[],
  providerList: ProviderResponse[] = providers,
): Promise<VueWrapper> {
  useCatalog(onRouteList, providerList)
  const wrapper = mount(ModelsView, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('加权模型路由管理', () => {
  it('清楚标注提供商原始模型名并说明别名重写', async () => {
    const wrapper = mount(RouteFormDrawer, {
      props: {
        modelValue: true,
        model: models[0] ?? null,
        route: null,
        providers,
        submitting: false,
      },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.text()).toContain('提供商原始模型名')
    expect(wrapper.text()).toContain('别名在转发前会转换为这里填写的模型名')
    wrapper.unmount()
  })

  it('路由只关联供应商并提交选定模型上下文', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(RouteFormDrawer, {
      props: {
        modelValue: true,
        model: models[0] ?? null,
        route: null,
        providers,
        submitting: false,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    const providerSelect = wrapper.get('[data-test="route-provider"]')
    expect(providerSelect.attributes('aria-label')).toBe('供应商')
    expect(wrapper.find('[data-test="route-protocol"]').exists()).toBe(false)

    await providerSelect.setValue('12')
    await wrapper.get('[data-test="route-upstream-model"]').setValue('gemini-2.5-pro')
    await wrapper.get('[data-test="route-weight"] input').setValue('500')
    await wrapper.get('[data-test="route-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({
      model_id: 1,
      provider_id: 12,
      upstream_model: 'gemini-2.5-pro',
      weight: 500,
      enabled: true,
    })
    wrapper.unmount()
  })

  it('编辑时只更新提供商关系', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(RouteFormDrawer, {
      props: {
        modelValue: true,
        model: models[0] ?? null,
        route: routeFixture,
        providers,
        submitting: false,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="route-provider"]').setValue('12')
    await wrapper.get('[data-test="route-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({
      provider_id: 12,
    })
    wrapper.unmount()
  })

  it('原生选择框有可访问名称，无提供商时显示校验空状态', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(RouteFormDrawer, {
      props: {
        modelValue: true,
        model: models[0] ?? null,
        route: null,
        providers: [],
        submitting: false,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.get('[data-test="route-provider"]').attributes('aria-label')).toBe('供应商')
    expect(wrapper.find('[data-test="route-protocol"]').exists()).toBe(false)
    await wrapper.get('[data-test="route-upstream-model"]').setValue('native-name')
    await wrapper.get('[data-test="route-submit"]').trigger('click')
    await waitForFormErrors()

    expect(wrapper.text()).toContain('请选择供应商')
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('序列化 model_id 和 provider_id 路由筛选参数', async () => {
    const requests: URL[] = []
    server.use(
      http.get('/admin/model-routes', ({ request }) => {
        requests.push(new URL(request.url))
        return HttpResponse.json([])
      }),
    )

    await listModelRoutes({ model_id: 2, provider_id: 12 })

    expect(requests).toHaveLength(1)
    expect(requests[0]?.searchParams.get('model_id')).toBe('2')
    expect(requests[0]?.searchParams.get('provider_id')).toBe('12')
  })

  it('权重只接受 1 到 10000 的整数并聚焦错误字段', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(RouteFormDrawer, {
      props: {
        modelValue: true,
        model: models[0] ?? null,
        route: null,
        providers,
        submitting: false,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="route-upstream-model"]').setValue('native-name')
    const weight = wrapper.get('[data-test="route-weight"] input')
    await weight.setValue('1.5')
    await wrapper.get('[data-test="route-submit"]').trigger('click')
    await waitForFormErrors()

    expect(wrapper.get('[data-validation="route-weight"] .el-form-item__error').text()).toContain(
      '1 到 10000 的整数',
    )
    expect(document.activeElement).toBe(weight.element)
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('每张模型卡从规范路由集合展示自己的只读来源和健康字段', async () => {
    const requestedModelIds: Array<string | null> = []
    const wrapper = await mountRoutes((url) => {
      const modelId = url.searchParams.get('model_id')
      requestedModelIds.push(modelId)
      const allRoutes = [routeFixture, closedRoute, openRoute]
      return modelId === null
        ? allRoutes
        : allRoutes.filter((route) => route.model_id === Number(modelId))
    })

    expect(requestedModelIds).toEqual([null])
    await wrapper.get('[data-test="model-card-1"] .routes-toggle').trigger('click')
    const firstCard = wrapper.get('[data-test="model-card-1"]')
    expect(firstCard.text()).toContain('自动发现')
    expect(firstCard.text()).toContain('探测中')
    expect(firstCard.text()).toContain('upstream_timeout')
    expect(firstCard.text()).toContain('连续失败: 3')
    expect(firstCard.text()).toContain('健康')
    expect(firstCard.text()).toContain('OpenAI / Claude')

    await wrapper.get('[data-test="model-card-2"] .routes-toggle').trigger('click')
    const secondCard = wrapper.get('[data-test="model-card-2"]')
    expect(secondCard.text()).toContain('不可用')
    expect(secondCard.text()).toContain('claude-opus-4-1')
    wrapper.unmount()
  })

  it('供应商停用时不把所属路由计为有效启用或可用', async () => {
    const disabledProviders = providers.map((provider) =>
      provider.id === 12 ? { ...provider, enabled: false } : provider,
    )
    const activeRoute = {
      ...closedRoute,
      id: 204,
      provider_id: 11,
      upstream_model: 'active-openai-model',
    }
    const disabledProviderRoute = {
      ...closedRoute,
      id: 205,
      provider_id: 12,
      upstream_model: 'disabled-provider-model',
    }
    const wrapper = await mountRoutes(() => [activeRoute, disabledProviderRoute], disabledProviders)
    const card = wrapper.get('[data-test="model-card-1"]')

    expect(card.text()).toContain('1/2 有效启用')
    expect(card.text()).toContain('1/2 可用')

    await card.get('.routes-toggle').trigger('click')
    expect(card.get('[data-test="route-status-205"]').text()).toContain('供应商停用')
    expect(card.get('[data-test="route-runtime-205"]').text()).toContain('健康')
    expect(card.get('[data-test="route-item-205"]').classes()).toContain('is-disabled')
    wrapper.unmount()
  })

  it('图标路由操作使用包含上游模型名的可访问名称', async () => {
    const wrapper = await mountRoutes()

    await wrapper.get('[data-test="model-card-1"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="model-card-2"] .routes-toggle').trigger('click')

    expect(wrapper.get('[data-test="edit-route-201"]').attributes('aria-label')).toBe(
      '编辑路由 gpt-4.1-2026-04-14',
    )
    expect(wrapper.get('[data-test="delete-route-201"]').attributes('aria-label')).toBe(
      '删除路由 gpt-4.1-2026-04-14',
    )
    expect(wrapper.get('[data-test="edit-route-203"]').attributes('aria-label')).toBe(
      '编辑路由 claude-opus-4-1',
    )
    expect(wrapper.get('[data-test="delete-route-203"]').attributes('aria-label')).toBe(
      '删除路由 claude-opus-4-1',
    )
    wrapper.unmount()
  })

  it('允许编辑自动发现路由但来源和运行状态不进入 PATCH', async () => {
    const patchBodies: unknown[] = []
    useCatalog()
    server.use(
      http.patch('/admin/model-routes/201', async ({ request }) => {
        patchBodies.push(await request.json())
        return HttpResponse.json({ ...routeFixture, weight: 900 })
      }),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="model-card-1"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="edit-route-201"]').trigger('click')
    const drawer = wrapper.getComponent(RouteFormDrawer)
    await drawer.get('[data-test="route-weight"] input').setValue('900')
    await drawer.get('[data-test="route-submit"]').trigger('click')
    await flushPromises()

    expect(patchBodies).toEqual([{ weight: 900 }])
    expect(JSON.stringify(patchBodies)).not.toContain('source')
    expect(JSON.stringify(patchBodies)).not.toContain('runtime_state')
    wrapper.unmount()
  })

  it('编辑非初始模型卡的路由并显示保存通知', async () => {
    const patchBodies: unknown[] = []
    useCatalog()
    server.use(
      http.patch('/admin/model-routes/203', async ({ request }) => {
        patchBodies.push(await request.json())
        return HttpResponse.json({ ...openRoute, weight: 640 })
      }),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="model-card-2"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="edit-route-203"]').trigger('click')
    const drawer = wrapper.getComponent(RouteFormDrawer)
    await drawer.get('[data-test="route-weight"] input').setValue('640')
    await drawer.get('[data-test="route-submit"]').trigger('click')
    await flushPromises()

    expect(patchBodies).toEqual([{ weight: 640 }])
    expect(wrapper.get('[data-test="route-notice"]').text()).toContain('已保存')
    wrapper.unmount()
  })

  it('删除路由后立即移除对应路由卡片', async () => {
    useCatalog()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(
      http.delete('/admin/model-routes/203', () => new HttpResponse(null, { status: 204 })),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="model-card-2"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="delete-route-203"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="edit-route-203"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="route-notice"]').text()).toContain('已删除')
    wrapper.unmount()
  })

  it('从非初始模型卡直接停用路由并更新该行状态', async () => {
    const patchBodies: unknown[] = []
    useCatalog()
    server.use(
      http.patch('/admin/model-routes/203', async ({ request }) => {
        patchBodies.push(await request.json())
        return HttpResponse.json({ ...openRoute, enabled: false })
      }),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="model-card-2"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="disable-route-203"]').trigger('click')
    await flushPromises()

    expect(patchBodies).toEqual([{ enabled: false }])
    expect(wrapper.get('[data-test="route-status-203"]').text()).toContain('已停用')
    wrapper.unmount()
  })

  it('只为已启用且不健康的路由显示手动恢复操作', async () => {
    const wrapper = await mountRoutes()

    await wrapper.get('[data-test="model-card-1"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="model-card-2"] .routes-toggle').trigger('click')

    expect(wrapper.find('[data-test="recover-route-201"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="recover-route-202"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="recover-route-203"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('恢复路由调用专用接口并更新健康状态和通知', async () => {
    const requests: Request[] = []
    useCatalog()
    server.use(
      http.post('/admin/model-routes/203/recover', ({ request }) => {
        requests.push(request)
        return HttpResponse.json({
          ...openRoute,
          runtime_state: 'closed',
          consecutive_failures: 0,
          disabled_until: null,
          last_error_code: null,
          last_error_at: null,
        })
      }),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="model-card-2"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="recover-route-203"]').trigger('click')
    await flushPromises()

    expect(requests).toHaveLength(1)
    expect(await requests[0]?.text()).toBe('')
    expect(wrapper.get('[data-test="model-card-2"]').text()).toContain('健康')
    expect(wrapper.find('[data-test="recover-route-203"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="route-notice"]').text()).toContain('已恢复')
    wrapper.unmount()
  })

  it('恢复响应编号不匹配时不改写路由且恢复失败可见', async () => {
    useCatalog()
    server.use(
      http.post('/admin/model-routes/203/recover', () =>
        HttpResponse.json({ ...openRoute, id: 202, runtime_state: 'closed' }),
      ),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="model-card-2"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="recover-route-203"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="model-card-2"]').text()).toContain('不可用')
    expect(wrapper.find('[data-test="route-notice"]').exists()).toBe(false)

    server.use(
      http.post('/admin/model-routes/203/recover', () =>
        HttpResponse.json(
          { detail: { code: 'recovery_unavailable', message: '恢复服务暂不可用' } },
          { status: 503 },
        ),
      ),
    )
    await wrapper.get('[data-test="recover-route-203"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="route-notice"]').text()).toContain('服务暂时不可用')
    wrapper.unmount()
  })

  it('停用响应的路由编号不匹配时不改写其他路由或显示成功', async () => {
    useCatalog()
    server.use(
      http.patch('/admin/model-routes/203', () =>
        HttpResponse.json({ ...openRoute, id: 202, enabled: false }),
      ),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="model-card-1"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="model-card-2"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="disable-route-203"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="model-card-1"] [data-test="edit-route-202"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="route-status-203"]').text()).toContain('已启用')
    expect(wrapper.find('[data-test="route-notice"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('路由草稿在提交时不因父级上下文变化而重置', async () => {
    const wrapper = mount(RouteFormDrawer, {
      props: {
        modelValue: true,
        model: models[0] ?? null,
        route: routeFixture,
        providers,
        submitting: false,
      },
      attachTo: document.body,
    })
    await flushPromises()
    await wrapper.get('[data-test="route-upstream-model"]').setValue('pending-draft')

    await wrapper.setProps({ submitting: true })
    await wrapper.setProps({ model: models[1] ?? null, route: closedRoute })
    await wrapper.setProps({ modelValue: false })

    expect(wrapper.get('[data-test="route-upstream-model"]').element).toHaveProperty(
      'value',
      'pending-draft',
    )
    wrapper.unmount()
  })

  it('路由保存时锁定模型上下文并在卸载时废弃结果', async () => {
    const response = deferred<ModelRouteResponse>()
    useCatalog()
    server.use(
      http.patch('/admin/model-routes/201', async () => HttpResponse.json(await response.promise)),
    )
    const confirm = vi.spyOn(ElMessageBox, 'confirm')
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="model-card-1"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="edit-route-201"]').trigger('click')
    const drawer = wrapper.getComponent(RouteFormDrawer)
    await drawer.get('[data-test="route-weight"] input').setValue('901')
    await drawer.get('[data-test="route-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="edit-model-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="delete-model-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="edit-model-2"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="create-route-2"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="delete-model-1"]').trigger('click')
    expect(confirm).not.toHaveBeenCalled()

    wrapper.unmount()
    response.resolve({ ...routeFixture, weight: 901 })
    await flushPromises()
    expect(document.body.textContent).not.toContain('模型路由已保存')
  })

  it('待确认的模型删除锁定所有卡片的路由创建操作', async () => {
    useCatalog()
    const confirmation = deferred<MessageBoxData>()
    vi.spyOn(ElMessageBox, 'confirm').mockReturnValue(confirmation.promise)
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="delete-model-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="create-route-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="create-route-2"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="create-route-2"]').trigger('click')

    expect(wrapper.findComponent(RouteFormDrawer).props('modelValue')).toBe(false)
    wrapper.unmount()
    confirmation.resolve({ value: '', action: 'confirm' } as MessageBoxData)
  })

  it('路由删除期间锁定模型选择和模型操作', async () => {
    useCatalog()
    const deletion = deferred<undefined>()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(
      http.delete('/admin/model-routes/201', async () => {
        await deletion.promise
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="model-card-1"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="delete-route-201"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="edit-model-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="delete-model-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="edit-model-2"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="create-route-2"]').attributes('disabled')).toBeDefined()

    deletion.resolve(undefined)
    await flushPromises()
    wrapper.unmount()
  })

  it('创建和删除路由后更新模型的路由数', async () => {
    useCatalog()
    const createdRoute: ModelRouteResponse = {
      ...routeFixture,
      id: 204,
      upstream_model: 'new-native-model',
    }
    server.use(
      http.post('/admin/model-routes', () => HttpResponse.json(createdRoute)),
      http.delete('/admin/model-routes/204', () => new HttpResponse(null, { status: 204 })),
    )
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    expect(wrapper.get('[data-test="route-count-1"]').text()).toBe('2')
    await wrapper.get('[data-test="create-route-1"]').trigger('click')
    const drawer = wrapper.getComponent(RouteFormDrawer)
    await drawer.get('[data-test="route-upstream-model"]').setValue('new-native-model')
    await drawer.get('[data-test="route-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="route-count-1"]').text()).toBe('3')

    await wrapper.get('[data-test="model-card-1"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="delete-route-204"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="route-count-1"]').text()).toBe('2')
    wrapper.unmount()
  })

  it('成功删除路由并保留当前模型上下文', async () => {
    useCatalog()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(http.delete('/admin/model-routes/201', () => new HttpResponse(null, { status: 204 })))
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="model-card-1"] .routes-toggle').trigger('click')
    await wrapper.get('[data-test="delete-route-201"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="edit-route-201"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="model-card-1"]').text()).toContain('GPT 4.1')
    expect(wrapper.get('[data-test="route-notice"]').text()).toContain('已删除')
    wrapper.unmount()
  })

  it('忽略本地修订后才返回的过期路由失败', async () => {
    const staleCatalog = deferred<undefined>()
    useCatalog()
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    server.use(
      http.get('/admin/model-routes', async ({ request }) => {
        if (new URL(request.url).searchParams.get('model_id') === null) {
          await staleCatalog.promise
          return HttpResponse.json({ detail: 'stale route failure' }, { status: 500 })
        }
        return HttpResponse.json([])
      }),
      http.post('/admin/model-routes', () =>
        HttpResponse.json({ ...routeFixture, id: 204, upstream_model: 'local-route' }),
      ),
    )

    await wrapper.get('[data-test="create-route-1"]').trigger('click')
    const drawer = wrapper.getComponent(RouteFormDrawer)
    await drawer.get('[data-test="route-upstream-model"]').setValue('local-route')
    const view = wrapper.vm as unknown as { load: () => Promise<void> }
    const staleLoad = view.load()
    await flushPromises()
    expect(wrapper.get('[data-test="model-card-1"]').text()).toContain('加载中...')
    await drawer.get('[data-test="route-submit"]').trigger('click')
    await flushPromises()
    staleCatalog.resolve(undefined)
    await staleLoad
    await flushPromises()

    expect(wrapper.text()).toContain('local-route')
    expect(wrapper.text()).not.toContain('stale route failure')
    wrapper.unmount()
  })

  it('本地创建后不让过期路由成功覆盖详情和路由数', async () => {
    useCatalog()
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    const staleResponse = deferred<undefined>()
    server.use(
      http.get('/admin/model-routes', async ({ request }) => {
        const modelId = new URL(request.url).searchParams.get('model_id')
        if (modelId === null) {
          await staleResponse.promise
          return HttpResponse.json([routeFixture])
        }
        return HttpResponse.json([])
      }),
      http.post('/admin/model-routes', () =>
        HttpResponse.json({
          ...routeFixture,
          id: 204,
          upstream_model: 'locally-created-route',
        }),
      ),
    )
    await wrapper.get('[data-test="create-route-1"]').trigger('click')
    const drawer = wrapper.getComponent(RouteFormDrawer)
    await drawer.get('[data-test="route-upstream-model"]').setValue('locally-created-route')
    const view = wrapper.vm as unknown as { load: () => Promise<void> }
    const staleLoad = view.load()
    await flushPromises()
    await drawer.get('[data-test="route-submit"]').trigger('click')
    await flushPromises()

    staleResponse.resolve(undefined)
    await staleLoad
    await flushPromises()
    expect(wrapper.text()).toContain('locally-created-route')
    expect(wrapper.get('[data-test="route-count-1"]').text()).toBe('3')
    wrapper.unmount()
  })
})
