import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessageBox, type MessageBoxData } from 'element-plus'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import type { ModelResponse, ModelRouteResponse, ProviderResponse } from '@/api/types'
import RouteFormDrawer from '@/components/models/RouteFormDrawer.vue'
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
    enabled: true,
    auto_load_models: false,
    model_sync_interval_seconds: 3600,
    last_model_sync_at: null,
    protocols: [
      {
        id: 111,
        protocol: 'openai',
        base_url: 'https://openai.example.com/v1',
        websocket_url: null,
        has_extra_headers: false,
        enabled: true,
      },
      {
        id: 112,
        protocol: 'claude',
        base_url: 'https://claude.example.com',
        websocket_url: null,
        has_extra_headers: false,
        enabled: true,
      },
    ],
  },
  {
    id: 12,
    name: 'Gemini 备用线路',
    has_credential: true,
    enabled: true,
    auto_load_models: false,
    model_sync_interval_seconds: 3600,
    last_model_sync_at: null,
    protocols: [
      {
        id: 121,
        protocol: 'gemini',
        base_url: 'https://gemini.example.com',
        websocket_url: null,
        has_extra_headers: false,
        enabled: true,
      },
    ],
  },
]

const routeFixture: ModelRouteResponse = {
  id: 201,
  model_id: 1,
  provider_id: 11,
  provider_protocol_id: 111,
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
  provider_protocol_id: 121,
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

function useCatalog(onRouteList?: (url: URL) => ModelRouteResponse[]): void {
  server.use(
    http.get('/admin/models', () => HttpResponse.json(models)),
    http.get('/admin/providers', () => HttpResponse.json(providers)),
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

async function mountRoutes(onRouteList?: (url: URL) => ModelRouteResponse[]): Promise<VueWrapper> {
  useCatalog(onRouteList)
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

  it('提供商选择只显示其协议编号并提交选定模型上下文', async () => {
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
    const protocolSelect = wrapper.get('[data-test="route-protocol"]')
    expect(protocolSelect.findAll('option').map((option) => option.attributes('value'))).toEqual([
      '111',
      '112',
    ])

    await providerSelect.setValue('12')
    expect(protocolSelect.findAll('option').map((option) => option.attributes('value'))).toEqual([
      '121',
    ])
    await wrapper.get('[data-test="route-upstream-model"]').setValue('gemini-2.5-pro')
    await wrapper.get('[data-test="route-weight"] input').setValue('500')
    await wrapper.get('[data-test="route-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({
      model_id: 1,
      provider_id: 12,
      provider_protocol_id: 121,
      upstream_model: 'gemini-2.5-pro',
      weight: 500,
      enabled: true,
    })
    wrapper.unmount()
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

  it('选择模型时按 model_id 加载路由并展示只读来源和健康字段', async () => {
    const requestedModelIds: Array<string | null> = []
    const wrapper = await mountRoutes((url) => {
      const modelId = url.searchParams.get('model_id')
      requestedModelIds.push(modelId)
      const allRoutes = [routeFixture, closedRoute, openRoute]
      return modelId === null
        ? allRoutes
        : allRoutes.filter((route) => route.model_id === Number(modelId))
    })

    expect(requestedModelIds).toContain('1')
    expect(wrapper.get('[data-test="route-panel"]').text()).toContain('自动发现')
    expect(wrapper.get('[data-test="route-panel"]').text()).toContain('探测中')
    expect(wrapper.get('[data-test="route-panel"]').text()).toContain('upstream_timeout')
    expect(wrapper.get('[data-test="route-panel"]').text()).toContain('3')
    expect(wrapper.get('[data-test="route-panel"]').text()).toContain('健康')

    await wrapper.get('[data-test="select-model-2"]').trigger('click')
    await flushPromises()
    expect(requestedModelIds).toContain('2')
    expect(wrapper.get('[data-test="route-panel"]').text()).toContain('不可用')
    expect(wrapper.get('[data-test="route-panel"]').text()).toContain('claude-opus-4-1')
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

  it('路由有历史记录时保留记录并提供真实的停用 PATCH 操作', async () => {
    const patchBodies: unknown[] = []
    useCatalog()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(
      http.delete('/admin/model-routes/201', () =>
        HttpResponse.json(
          {
            detail: {
              code: 'model_route_has_history',
              message: 'Routes with request history must be disabled instead of deleted',
            },
          },
          { status: 409 },
        ),
      ),
      http.patch('/admin/model-routes/201', async ({ request }) => {
        patchBodies.push(await request.json())
        return HttpResponse.json({ ...routeFixture, enabled: false })
      }),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="delete-route-201"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('gpt-4.1-2026-04-14')
    expect(wrapper.get('[data-test="route-notice"]').text()).toContain('请求历史')

    await wrapper.get('[data-test="disable-route-201"]').trigger('click')
    await flushPromises()
    expect(patchBodies).toEqual([{ enabled: false }])
    expect(wrapper.get('[data-test="route-status-201"]').text()).toContain('已停用')
    wrapper.unmount()
  })
})
