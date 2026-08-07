import { flushPromises, mount } from '@vue/test-utils'
import { ElMessageBox, type MessageBoxData } from 'element-plus'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  CurrentUser,
  ModelResponse,
  ModelRouteResponse,
  ProviderResponse,
} from '@/api/types'
import ModelCard from '@/components/models/ModelCard.vue'
import ModelFormDrawer from '@/components/models/ModelFormDrawer.vue'
import RouteFormDrawer from '@/components/models/RouteFormDrawer.vue'
import { routes } from '@/router'
import { useAuthStore } from '@/stores/auth'
import ModelsView from '@/views/ModelsView.vue'

vi.mock('vue-echarts', () => ({
  default: defineComponent({
    name: 'VChartStub',
    props: { option: { type: Object, required: true } },
    template: '<div class="v-chart-stub" />',
  }),
}))

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

const modelFixture: ModelResponse = {
  id: 1,
  canonical_name: 'gpt-4.1',
  display_name: 'GPT 4.1',
  input_price_per_million: '2.00000000',
  output_price_per_million: '8.00000000',
  cache_read_price_per_million: '0.50000000',
  cache_write_price_per_million: '2.50000000',
  price_multiplier: 1.0,
  enabled: true,
  aliases: [
    { id: 101, alias: 'fast-chat', enabled: true },
    { id: 102, alias: 'legacy-chat', enabled: false },
  ],
  routing_strategy: 'weighted_random',
  created_at: '2026-07-22T08:00:00Z',
  updated_at: '2026-07-22T08:00:00Z',
}

const scientificZeroFixture: ModelResponse = {
  ...modelFixture,
  id: 2,
  canonical_name: 'zero-price-model',
  display_name: '零价格模型',
  input_price_per_million: '0E-8',
  output_price_per_million: '0E-8',
  cache_read_price_per_million: '0E-8',
  cache_write_price_per_million: '0E-8',
  aliases: [],
}

const providerFixture: ProviderResponse = {
  id: 11,
  name: 'OpenAI 主线路',
  has_credential: true,
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
      base_url: 'https://api.example.com/v1',
      websocket_url: null,
      has_extra_headers: false,
      supports_responses: true,
      enabled: true,
    },
  ],
}

const routeFixture: ModelRouteResponse = {
  id: 201,
  model_id: 1,
  provider_id: 11,
  upstream_model: 'gpt-4.1-2026-04-14',
  weight: 100,
  enabled: true,
  source: 'manual',
  runtime_state: 'closed',
  consecutive_failures: 0,
  disabled_until: null,
  last_error_code: null,
  last_error_at: null,
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
  models: ModelResponse[] = [modelFixture],
  modelRoutes: ModelRouteResponse[] = [routeFixture],
  providers: ProviderResponse[] = [providerFixture],
): void {
  server.use(
    http.get('/admin/models', () => HttpResponse.json(models)),
    http.get('/admin/providers', () => HttpResponse.json(providers)),
    http.get('/admin/model-routes', ({ request }) => {
      const modelId = new URL(request.url).searchParams.get('model_id')
      return HttpResponse.json(
        modelId === null
          ? modelRoutes
          : modelRoutes.filter((route) => route.model_id === Number(modelId)),
      )
    }),
  )
}

describe('模型与别名管理', () => {
  it('通过独立懒加载路由提供模型页面', async () => {
    const shellRoute = routes.find((route) => route.path === '/')
    const modelRoute = shellRoute?.children?.find((route) => route.name === 'models')
    if (typeof modelRoute?.component !== 'function') {
      throw new Error('模型路由不是懒加载组件')
    }

    const loadModels = modelRoute.component as () => Promise<{ default: unknown }>
    const loadedModule = await loadModels()
    expect(loadedModule.default).toBe(ModelsView)
  })

  it('普通用户只从自助目录浏览可用模型且看不到管理和路由信息', async () => {
    useAuthStore().user = regularUser
    let adminModelsRequests = 0
    let providerRequests = 0
    let routeRequests = 0
    server.use(
      http.get('/user/models', () =>
        HttpResponse.json([
          {
            ...modelFixture,
            aliases: modelFixture.aliases.filter((alias) => alias.enabled),
          },
        ]),
      ),
      http.get('/admin/models', () => {
        adminModelsRequests += 1
        return HttpResponse.json([])
      }),
      http.get('/admin/providers', () => {
        providerRequests += 1
        return HttpResponse.json([])
      }),
      http.get('/admin/model-routes', () => {
        routeRequests += 1
        return HttpResponse.json([])
      }),
    )

    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    expect(wrapper.get('.page-header h1').text()).toBe('可用模型')
    expect(wrapper.get('[data-test="model-card-1"]').text()).toContain('GPT 4.1')
    expect(wrapper.text()).toContain('fast-chat')
    expect(wrapper.text()).not.toContain('legacy-chat')
    expect(wrapper.find('[data-test="create-model"]').exists()).toBe(false)
    expect(wrapper.find('[data-test^="edit-model-"]').exists()).toBe(false)
    expect(wrapper.find('[data-test^="delete-model-"]').exists()).toBe(false)
    expect(wrapper.find('[data-test^="create-route-"]').exists()).toBe(false)
    expect(wrapper.find('[data-test^="price-comparison-toggle-"]').exists()).toBe(false)
    expect(wrapper.find('[data-test^="compare-model-"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="price-comparison-open"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('模型路由')
    expect(wrapper.text()).not.toContain('成本倍率')
    expect(wrapper.findComponent(ModelFormDrawer).exists()).toBe(false)
    expect(wrapper.findComponent(RouteFormDrawer).exists()).toBe(false)
    expect(adminModelsRequests).toBe(0)
    expect(providerRequests).toBe(0)
    expect(routeRequests).toBe(0)
    wrapper.unmount()
  })

  it('将启用模型按可用、无可用路由和无健康路由分区', async () => {
    const noUsableRoute = { ...scientificZeroFixture, id: 3, canonical_name: 'no-usable-route' }
    const unhealthyRoute = { ...scientificZeroFixture, id: 4, canonical_name: 'unhealthy-route' }
    useCatalog(
      [modelFixture, noUsableRoute, unhealthyRoute],
      [
        routeFixture,
        { ...routeFixture, id: 203, model_id: unhealthyRoute.id, runtime_state: 'open' },
      ],
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    const availableGroup = wrapper.get('[data-test="available-model-group"]')
    const noUsableRouteGroup = wrapper.get('[data-test="no-usable-route-model-group"]')
    const unhealthyRouteGroup = wrapper.get('[data-test="unhealthy-route-model-group"]')
    expect(availableGroup.text()).toContain('可用')
    expect(availableGroup.find('[data-test="model-card-1"]').exists()).toBe(true)
    expect(noUsableRouteGroup.text()).toContain('无可用路由')
    expect(noUsableRouteGroup.find('[data-test="model-card-3"]').exists()).toBe(true)
    expect(unhealthyRouteGroup.text()).toContain('无健康路由')
    expect(unhealthyRouteGroup.find('[data-test="model-card-4"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('将停用模型独立分区并显示数量', async () => {
    const disabledModel = { ...scientificZeroFixture, enabled: false }
    useCatalog([modelFixture, disabledModel], [])
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    const noUsableRouteGroup = wrapper.get('[data-test="no-usable-route-model-group"]')
    const disabledGroup = wrapper.get('[data-test="disabled-model-group"]')
    expect(noUsableRouteGroup.text()).toContain('无可用路由')
    expect(noUsableRouteGroup.text()).toContain('1 个')
    expect(noUsableRouteGroup.find('[data-test="model-card-1"]').exists()).toBe(true)
    expect(noUsableRouteGroup.find('[data-test="model-card-2"]').exists()).toBe(false)
    expect(disabledGroup.text()).toContain('已停用')
    expect(disabledGroup.text()).toContain('1 个')
    expect(disabledGroup.find('[data-test="model-card-2"]').exists()).toBe(true)
    expect(disabledGroup.find('[data-test="model-card-1"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('通过快捷操作停用模型并将它移入已停用分区', async () => {
    const patchBodies: unknown[] = []
    useCatalog()
    server.use(
      http.patch('/admin/models/1', async ({ request }) => {
        patchBodies.push(await request.json())
        return HttpResponse.json({ ...modelFixture, enabled: false })
      }),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="toggle-model-1"]').trigger('click')
    await flushPromises()

    expect(patchBodies).toEqual([{ enabled: false }])
    expect(wrapper.get('[data-test="disabled-model-group"]').find('[data-test="model-card-1"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('将模型操作按钮置于标题下方的独立一行', async () => {
    useCatalog()
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    const card = wrapper.get('[data-test="model-card-1"]')
    expect(card.find('.card-header .card-actions').exists()).toBe(false)
    expect(card.find('.card-header + .card-actions').exists()).toBe(true)
    wrapper.unmount()
  })

  it('提交启用状态别名对象并原样保留精确价格字符串', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ModelFormDrawer, {
      props: { modelValue: true, model: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="model-canonical-name"]').setValue('gpt-4.1')
    await wrapper.get('[data-test="model-display-name"]').setValue('GPT 4.1')
    await wrapper.get('[data-test="model-input-price"]').setValue('2.00000000')
    await wrapper.get('[data-test="model-output-price"]').setValue('8.00000000')
    await wrapper.get('[data-test="model-cache-read-price"]').setValue('0.50000000')
    await wrapper.get('[data-test="model-cache-write-price"]').setValue('2.50000000')
    await wrapper.get('[data-test="add-model-alias"]').trigger('click')
    await wrapper.get('[data-test="model-alias-0"]').setValue('fast-chat')
    await wrapper.get('[data-test="model-alias-enabled-0"]').trigger('click')
    await wrapper.get('[data-test="model-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({
      canonical_name: 'gpt-4.1',
      display_name: 'GPT 4.1',
      input_price_per_million: '2.00000000',
      output_price_per_million: '8.00000000',
      cache_read_price_per_million: '0.50000000',
      cache_write_price_per_million: '2.50000000',
      price_multiplier: 1.0,
      price_tiers: [],
      enabled: true,
      aliases: [{ alias: 'fast-chat', enabled: false }],
      routing_strategy: 'weighted_random',
    })
    wrapper.unmount()
  })

  it('在模型卡片展示缓存读写价格', async () => {
    useCatalog()
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    expect(wrapper.text()).toContain('缓存读取价格：')
    expect(wrapper.text()).toContain('缓存写入价格：')
    expect(wrapper.text()).toContain('¥0.50000000')
    expect(wrapper.text()).toContain('¥2.50000000')
    wrapper.unmount()
  })

  it('默认收起分段价格，并在展开后展示每个分段的长度范围与四类价格', async () => {
    const wrapper = mount(ModelCard, {
      props: {
        model: {
          ...modelFixture,
          price_tiers: [
            {
              id: 301,
              max_input_tokens: 272000,
              input_price_per_million: '3.00000000',
              output_price_per_million: '15.00000000',
              cache_read_price_per_million: '0.30000000',
              cache_write_price_per_million: '3.75000000',
            },
            {
              id: 302,
              max_input_tokens: null,
              input_price_per_million: '6.00000000',
              output_price_per_million: '22.50000000',
              cache_read_price_per_million: '0.60000000',
              cache_write_price_per_million: '7.50000000',
            },
          ],
        },
        routes: [],
        providers: [],
      },
    })

    expect(wrapper.find('[data-test="model-price-tier-301"]').exists()).toBe(false)
    await wrapper.get('[data-test="model-price-details-1"]').trigger('click')

    const tiers = wrapper.findAll('[data-test^="model-price-tier-"]')
    expect(tiers).toHaveLength(2)
    expect(tiers[0]?.get('.price-tier__header').text()).toContain('Length ≤ 272K')
    expect(tiers[1]?.get('.price-tier__header').text()).toContain('不限长度')
    expect(
      tiers[0]?.findAll('.price-metric').map((metric) => [
        metric.get('.price-metric__label').text(),
        metric.get('.price-metric__value').text(),
      ]),
    ).toEqual([
      ['输入', '¥3.00000000'],
      ['输出', '¥15.00000000'],
      ['缓存读取', '¥0.30000000'],
      ['缓存写入', '¥3.75000000'],
    ])
    wrapper.unmount()
  })

  it('勾选多个模型后按模型分段对比价格范围，并排除不可用的价格来源', async () => {
    const firstModel = {
      ...modelFixture,
      price_multiplier: '1.25',
    } satisfies ModelResponse
    const firstProvider = {
      ...providerFixture,
      cost_multiplier: '0.50',
      public_multiplier: '2.00',
    } satisfies ProviderResponse
    const secondProvider = {
      ...providerFixture,
      id: 12,
      name: '第二供应商不应展示',
      cost_multiplier: '1.50',
      public_multiplier: '3.00',
      protocols: providerFixture.protocols.map((protocol) => ({ ...protocol, id: 121 })),
    } satisfies ProviderResponse
    const disabledProvider = {
      ...providerFixture,
      id: 13,
      name: '停用供应商不应计价',
      enabled: false,
      cost_multiplier: '9.00',
      public_multiplier: '9.00',
      protocols: providerFixture.protocols.map((protocol) => ({ ...protocol, id: 131 })),
    } satisfies ProviderResponse
    const noProtocolProvider = {
      ...providerFixture,
      id: 14,
      name: '无协议供应商不应计价',
      cost_multiplier: '8.00',
      public_multiplier: '8.00',
      protocols: providerFixture.protocols.map((protocol) => ({
        ...protocol,
        id: 141,
        enabled: false,
      })),
    } satisfies ProviderResponse
    const disabledRouteProvider = {
      ...providerFixture,
      id: 15,
      name: '停用路由供应商不应计价',
      cost_multiplier: '7.00',
      public_multiplier: '7.00',
      protocols: providerFixture.protocols.map((protocol) => ({ ...protocol, id: 151 })),
    } satisfies ProviderResponse
    const secondModel = {
      ...scientificZeroFixture,
      display_name: 'Claude Sonnet',
      canonical_name: 'claude-sonnet',
      input_price_per_million: '4.00000000',
      output_price_per_million: '12.00000000',
      cache_read_price_per_million: '1.00000000',
      cache_write_price_per_million: '3.00000000',
      price_tiers: [
        {
          id: 401,
          max_input_tokens: 272000,
          input_price_per_million: '4.00000000',
          output_price_per_million: '12.00000000',
          cache_read_price_per_million: '1.00000000',
          cache_write_price_per_million: '3.00000000',
        },
        {
          id: 402,
          max_input_tokens: null,
          input_price_per_million: '5.00000000',
          output_price_per_million: '15.00000000',
          cache_read_price_per_million: '1.50000000',
          cache_write_price_per_million: '4.00000000',
        },
      ],
    } satisfies ModelResponse
    useCatalog(
      [firstModel, secondModel],
      [
        routeFixture,
        { ...routeFixture, id: 202, model_id: secondModel.id, provider_id: secondProvider.id },
        { ...routeFixture, id: 203, provider_id: secondProvider.id },
        { ...routeFixture, id: 204, provider_id: disabledProvider.id },
        { ...routeFixture, id: 205, provider_id: noProtocolProvider.id },
        { ...routeFixture, id: 206, provider_id: disabledRouteProvider.id, enabled: false },
      ],
      [
        firstProvider,
        secondProvider,
        disabledProvider,
        noProtocolProvider,
        disabledRouteProvider,
      ],
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    const openButton = wrapper.get('[data-test="price-comparison-open"]')
    expect(openButton.attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="compare-model-1"]').trigger('click')
    expect(openButton.attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="compare-model-2"]').trigger('click')
    expect(openButton.attributes('disabled')).toBeUndefined()
    await openButton.trigger('click')
    await flushPromises()

    const comparison = document.querySelector<HTMLElement>(
      '[data-test="model-price-comparison-dialog"]',
    )
    expect(comparison).not.toBeNull()
    expect(comparison?.textContent).toContain('GPT 4.1')
    expect(comparison?.textContent).toContain('Claude Sonnet')
    expect(comparison?.textContent).toContain('Length ≤ 272K')
    expect(comparison?.textContent).toContain('¥1.25000000 – ¥3.75000000')
    expect(comparison?.textContent).toContain('¥5.00000000 – ¥7.50000000')
    expect(comparison?.textContent).toContain('¥6.00000000')
    expect(comparison?.textContent).toContain('¥12.00000000')
    expect(comparison?.textContent).not.toContain('OpenAI 主线路')
    expect(comparison?.textContent).not.toContain('第二供应商不应展示')
    expect(comparison?.textContent).not.toContain('停用供应商不应计价')
    expect(comparison?.textContent).not.toContain('无协议供应商不应计价')
    expect(comparison?.textContent).not.toContain('停用路由供应商不应计价')
    expect(comparison?.querySelector('[data-test="model-comparison-summary"]')).not.toBeNull()
    expect(comparison?.querySelector('[data-test="model-comparison-chart"]')).not.toBeNull()
    expect(comparison?.textContent).toContain('已选模型')
    expect(comparison?.textContent).toContain('最低输入用户价')
    const chart = wrapper.getComponent({ name: 'VChartStub' })
    const option = chart.props('option') as {
      series: Array<{ name: string; type: string; data: Array<number | null> }>
    }
    expect(option.series).toEqual(expect.arrayContaining([
      expect.objectContaining({ name: '输入成本', type: 'bar', data: [1.25, 6, 7.5] }),
      expect.objectContaining({ name: '输入用户价格', type: 'bar', data: [5, 12, 15] }),
      expect.objectContaining({ name: '输出成本', type: 'bar', data: [5, 18, 22.5] }),
      expect.objectContaining({ name: '输出用户价格', type: 'bar', data: [20, 36, 45] }),
    ]))
    wrapper.unmount()
  })

  it('在紧凑分段编辑卡片中用 K 回填长度并按整数 Token 提交', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ModelFormDrawer, {
      props: {
        modelValue: true,
        model: {
          ...modelFixture,
          price_tiers: [
            {
              id: 301,
              max_input_tokens: 272000,
              input_price_per_million: '3.00000000',
              output_price_per_million: '15.00000000',
              cache_read_price_per_million: '0.30000000',
              cache_write_price_per_million: '3.75000000',
            },
            {
              id: 302,
              max_input_tokens: null,
              input_price_per_million: '6.00000000',
              output_price_per_million: '22.50000000',
              cache_read_price_per_million: '0.60000000',
              cache_write_price_per_million: '7.50000000',
            },
          ],
        },
        submitting: false,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    const rows = wrapper.findAll('.tier-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]?.get('.tier-limit-field').text()).toContain('长度上限')
    expect(
      (wrapper.get('[data-test="model-tier-limit-0"] input').element as HTMLInputElement).value,
    ).toBe('272')
    const unit = wrapper.get('[data-test="model-tier-limit-unit-0"]')
    expect(unit.element).toHaveProperty('value', 'k')
    await unit.setValue('token')
    expect(wrapper.get('[data-test="model-tier-limit-0"] input').element).toHaveProperty(
      'value',
      '272000',
    )
    await unit.setValue('k')
    await wrapper.get('[data-test="model-tier-limit-0"] input').setValue('1.001')
    expect(rows[1]?.get('.tier-limit-field').text()).toContain('不限长度（最终分段）')
    expect(rows[1]?.find('[data-test="model-tier-limit-1"]').exists()).toBe(false)
    expect(rows.every((row) => row.findAll('.tier-price-grid .el-form-item').length === 4)).toBe(
      true,
    )
    expect(wrapper.get('[data-test="model-tier-input-0"]').element).toHaveProperty(
      'value',
      '3.00000000',
    )
    expect(wrapper.get('[data-test="model-tier-output-0"]').element).toHaveProperty(
      'value',
      '15.00000000',
    )
    expect(wrapper.get('[data-test="model-tier-cache-read-1"]').element).toHaveProperty(
      'value',
      '0.60000000',
    )
    expect(wrapper.get('[data-test="model-tier-cache-write-1"]').element).toHaveProperty(
      'value',
      '7.50000000',
    )
    await wrapper.get('[data-test="model-submit"]').trigger('click')
    const payload = onSubmit.mock.calls[0]?.[0] as {
      price_tiers?: Array<{ max_input_tokens: number | null }>
    }
    expect(payload.price_tiers?.[0]?.max_input_tokens).toBe(1001)
    wrapper.unmount()
  })

  it('拒绝超过安全整数范围的分段长度', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ModelFormDrawer, {
      props: {
        modelValue: true,
        model: {
          ...modelFixture,
          price_tiers: [
            {
              id: 301,
              max_input_tokens: 272000,
              input_price_per_million: '3',
              output_price_per_million: '15',
              cache_read_price_per_million: '0.3',
              cache_write_price_per_million: '3.75',
            },
            {
              id: 302,
              max_input_tokens: null,
              input_price_per_million: '6',
              output_price_per_million: '22.5',
              cache_read_price_per_million: '0.6',
              cache_write_price_per_million: '7.5',
            },
          ],
        },
        submitting: false,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.get('[data-test="model-tier-limit-unit-0"]').element).toHaveProperty(
      'value',
      'k',
    )
    await wrapper
      .get('[data-test="model-tier-limit-0"] input')
      .setValue(String(Number.MAX_SAFE_INTEGER))
    await wrapper.get('[data-test="model-submit"]').trigger('click')
    await waitForFormErrors()

    expect(
      wrapper.get('[data-validation="model-price-tier-0"] .el-form-item__error').text(),
    ).toContain('安全整数')
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('增删分段后始终将最后一档标记为不限长度', async () => {
    const wrapper = mount(ModelFormDrawer, {
      props: { modelValue: true, model: null, submitting: false },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="add-model-price-tier"]').trigger('click')
    expect(wrapper.get('.tier-limit-field').text()).toContain('不限长度（最终分段）')

    await wrapper.get('[data-test="add-model-price-tier"]').trigger('click')
    const rows = wrapper.findAll('.tier-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]?.find('[data-test="model-tier-limit-0"]').exists()).toBe(true)
    expect(rows[1]?.get('.tier-limit-field').text()).toContain('不限长度（最终分段）')

    await wrapper.get('[data-test="remove-model-price-tier-1"]').trigger('click')
    expect(wrapper.findAll('.tier-row')).toHaveLength(1)
    expect(wrapper.get('.tier-limit-field').text()).toContain('不限长度（最终分段）')
    wrapper.unmount()
  })

  it('拒绝非法缓存价格并聚焦对应输入框', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ModelFormDrawer, {
      props: { modelValue: true, model: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="model-canonical-name"]').setValue('cache-priced')
    await wrapper.get('[data-test="model-display-name"]').setValue('缓存价格')
    const cacheReadPrice = wrapper.get('[data-test="model-cache-read-price"]')
    await cacheReadPrice.setValue('-1')
    await wrapper.get('[data-test="model-submit"]').trigger('click')
    await waitForFormErrors()

    expect(
      wrapper.get('[data-validation="model-cache-read-price"] .el-form-item__error').text(),
    ).toContain('最多 12 位整数和 8 位小数')
    expect(document.activeElement).toBe(cacheReadPrice.element)
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('编辑时只提交变化的缓存价格，并规范等价科学计数值', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ModelFormDrawer, {
      props: {
        modelValue: true,
        model: {
          ...modelFixture,
          cache_read_price_per_million: '5E-1',
          cache_write_price_per_million: '2.5E+0',
        },
        submitting: false,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.get('[data-test="model-cache-read-price"]').element).toHaveProperty(
      'value',
      '0.5',
    )
    expect(wrapper.get('[data-test="model-cache-write-price"]').element).toHaveProperty(
      'value',
      '2.5',
    )
    await wrapper.get('[data-test="model-cache-read-price"]').setValue('0.75000000')
    await wrapper.get('[data-test="model-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({ cache_read_price_per_million: '0.75000000' })
    wrapper.unmount()
  })

  it('仅用字符串规则把后端科学计数零规范为可编辑零值', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ModelFormDrawer, {
      props: {
        modelValue: true,
        model: scientificZeroFixture,
        submitting: false,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.get('[data-test="model-input-price"]').element).toHaveProperty('value', '0')
    expect(wrapper.get('[data-test="model-output-price"]').element).toHaveProperty('value', '0')
    expect(wrapper.get('[data-test="model-cache-read-price"]').element).toHaveProperty('value', '0')
    expect(wrapper.get('[data-test="model-cache-write-price"]').element).toHaveProperty('value', '0')
    await wrapper.get('[data-test="model-display-name"]').setValue('免费模型')
    await wrapper.get('[data-test="model-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({ display_name: '免费模型' })
    wrapper.unmount()
  })

  it('将后端负号科学计数零规范为零，但仍拒绝负数价格', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ModelFormDrawer, {
      props: {
        modelValue: true,
        model: {
          ...scientificZeroFixture,
          input_price_per_million: '-0E-8',
          output_price_per_million: '-0.000E+12',
        },
        submitting: false,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.get('[data-test="model-input-price"]').element).toHaveProperty('value', '0')
    expect(wrapper.get('[data-test="model-output-price"]').element).toHaveProperty('value', '0')
    await wrapper.get('[data-test="model-display-name"]').setValue('负号零价格模型')
    await wrapper.get('[data-test="model-submit"]').trigger('click')
    expect(onSubmit).toHaveBeenCalledWith({ display_name: '负号零价格模型' })

    onSubmit.mockClear()
    await wrapper.get('[data-test="model-input-price"]').setValue('-1E-8')
    await wrapper.get('[data-test="model-submit"]').trigger('click')
    await waitForFormErrors()
    expect(wrapper.get('[data-validation="model-input-price"] .el-form-item__error').text()).toContain(
      '最多 12 位整数和 8 位小数',
    )
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('用纯字符串展开非负 Decimal 科学计数价格', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ModelFormDrawer, {
      props: {
        modelValue: true,
        model: {
          ...modelFixture,
          input_price_per_million: '+1E-8',
          output_price_per_million: '1.23E+2',
        },
        submitting: false,
        onSubmit,
      },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.get('[data-test="model-input-price"]').element).toHaveProperty(
      'value',
      '0.00000001',
    )
    expect(wrapper.get('[data-test="model-output-price"]').element).toHaveProperty('value', '123')
    await wrapper.get('[data-test="model-display-name"]').setValue('科学计数价格')
    await wrapper.get('[data-test="model-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({ display_name: '科学计数价格' })
    wrapper.unmount()
  })

  it('允许别名与本模型规范名称相同', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ModelFormDrawer, {
      props: { modelValue: true, model: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="model-canonical-name"]').setValue('gpt-4.1')
    await wrapper.get('[data-test="model-display-name"]').setValue('GPT 4.1')
    await wrapper.get('[data-test="model-input-price"]').setValue('0')
    await wrapper.get('[data-test="model-output-price"]').setValue('0')
    await wrapper.get('[data-test="add-model-alias"]').trigger('click')
    await wrapper.get('[data-test="model-alias-0"]').setValue('gpt-4.1')
    await wrapper.get('[data-test="model-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        canonical_name: 'gpt-4.1',
        aliases: [{ alias: 'gpt-4.1', enabled: true }],
      }),
    )
    wrapper.unmount()
  })

  it('拒绝重复别名，并聚焦第一条错误', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ModelFormDrawer, {
      props: { modelValue: true, model: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="model-canonical-name"]').setValue('gpt-4.1')
    await wrapper.get('[data-test="model-display-name"]').setValue('GPT 4.1')
    await wrapper.get('[data-test="model-input-price"]').setValue('0')
    await wrapper.get('[data-test="model-output-price"]').setValue('0')
    await wrapper.get('[data-test="add-model-alias"]').trigger('click')
    await wrapper.get('[data-test="add-model-alias"]').trigger('click')
    const firstAlias = wrapper.get('[data-test="model-alias-0"]')
    await firstAlias.setValue('shared-alias')
    await wrapper.get('[data-test="model-alias-1"]').setValue('shared-alias')
    await wrapper.get('[data-test="model-submit"]').trigger('click')
    await waitForFormErrors()

    expect(wrapper.get('[data-validation="model-alias-1"] .el-form-item__error').text()).toContain(
      '别名不能重复',
    )
    expect(document.activeElement).toBe(wrapper.get('[data-test="model-alias-1"]').element)
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('价格只接受最多十二位整数和八位小数且不经过浮点转换', async () => {
    const onSubmit = vi.fn()
    const wrapper = mount(ModelFormDrawer, {
      props: { modelValue: true, model: null, submitting: false, onSubmit },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.get('[data-test="model-canonical-name"]').setValue('precise')
    await wrapper.get('[data-test="model-display-name"]').setValue('精确价格')
    const inputPrice = wrapper.get('[data-test="model-input-price"]')
    await inputPrice.setValue('1234567890123.000000001')
    await wrapper.get('[data-test="model-output-price"]').setValue('0E-8')
    await wrapper.get('[data-test="model-submit"]').trigger('click')
    await waitForFormErrors()

    expect(wrapper.get('[data-validation="model-input-price"] .el-form-item__error').text()).toContain(
      '最多 12 位整数和 8 位小数',
    )
    expect(document.activeElement).toBe(inputPrice.element)
    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('模型有历史记录时保留模型并提供真实的停用 PATCH 操作', async () => {
    const patchBodies: unknown[] = []
    useCatalog()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(
      http.delete('/admin/models/1', () =>
        HttpResponse.json(
          {
            detail: {
              code: 'model_has_history',
              message: 'Models with request history must be disabled instead of deleted',
            },
          },
          { status: 409 },
        ),
      ),
      http.patch('/admin/models/1', async ({ request }) => {
        patchBodies.push(await request.json())
        return HttpResponse.json({ ...modelFixture, enabled: false })
      }),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="delete-model-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('GPT 4.1')
    expect(wrapper.get('[data-test="model-notice"]').text()).toContain('请求历史')

    await wrapper.get('[data-test="disable-model-1"]').trigger('click')
    await flushPromises()
    expect(patchBodies).toEqual([{ enabled: false }])
    expect(wrapper.get('[data-test="model-status-1"]').text()).toContain('已停用')
    wrapper.unmount()
  })

  it('保存期间阻止关闭和替换草稿，卸载后响应不能污染新会话', async () => {
    const response = deferred<ModelResponse>()
    useCatalog([modelFixture, scientificZeroFixture])
    server.use(
      http.patch('/admin/models/1', async () => HttpResponse.json(await response.promise)),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="edit-model-1"]').trigger('click')
    const drawer = wrapper.getComponent(ModelFormDrawer)
    await drawer.get('[data-test="model-display-name"]').setValue('延迟保存模型')
    await drawer.get('[data-test="model-submit"]').trigger('click')
    await flushPromises()

    expect(drawer.get('[data-test="model-cancel"]').attributes('disabled')).toBeDefined()
    expect(drawer.find('.el-drawer__close-btn').exists()).toBe(false)
    await drawer.get('[data-test="model-cancel"]').trigger('click')
    await wrapper.get('[data-test="create-model"]').trigger('click')
    expect(drawer.text()).toContain('编辑模型')
    expect(drawer.get('[data-test="model-display-name"]').element).toHaveProperty(
      'value',
      '延迟保存模型',
    )

    wrapper.unmount()
    response.resolve({ ...modelFixture, display_name: '延迟保存模型' })
    await flushPromises()
    expect(document.body.textContent).not.toContain('模型设置已保存')
  })

  it('初始目录加载期间禁止创建和模型操作', async () => {
    const response = deferred<ModelResponse[]>()
    server.use(
      http.get('/admin/models', async () => HttpResponse.json(await response.promise)),
      http.get('/admin/providers', () => HttpResponse.json([providerFixture])),
      http.get('/admin/model-routes', () => HttpResponse.json([routeFixture])),
    )
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    expect(wrapper.get('[data-test="create-model"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="create-model"]').trigger('click')
    expect(wrapper.findComponent(ModelFormDrawer).props('modelValue')).toBe(false)

    response.resolve([modelFixture])
    await flushPromises()
    expect(wrapper.get('[data-test="create-model"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('在没有模型的目录中显示空状态', async () => {
    useCatalog([], [])
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    expect(wrapper.text()).toContain('暂无模型')
    expect(wrapper.find('[data-test^="model-card-"]').exists()).toBe(false)
    expect(wrapper.find('[data-test^="create-route-"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('成功删除模型后清理价格比对选择并保留其他独立模型卡片', async () => {
    useCatalog([modelFixture, scientificZeroFixture])
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(http.delete('/admin/models/1', () => new HttpResponse(null, { status: 204 })))
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    await wrapper.get('[data-test="compare-model-1"]').trigger('click')
    await wrapper.get('[data-test="compare-model-2"]').trigger('click')
    expect(wrapper.get('[data-test="price-comparison-open"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-test="delete-model-1"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="model-card-1"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="model-card-2"]').text()).toContain('零价格模型')
    expect(wrapper.get('[data-test="price-comparison-open"]').text()).toContain('（1）')
    expect(wrapper.get('[data-test="price-comparison-open"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="model-notice"]').text()).toContain('已删除')
    wrapper.unmount()
  })

  it('忽略本地修订后才返回的过期目录失败', async () => {
    useCatalog()
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    const reloadGate = deferred<undefined>()
    server.use(
      http.get('/admin/models', async () => {
        await reloadGate.promise
        return HttpResponse.json({ detail: 'stale catalog failure' }, { status: 500 })
      }),
      http.post('/admin/models', async ({ request }) => {
        const payload = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          ...modelFixture,
          ...payload,
          id: 3,
          aliases: [],
        })
      }),
    )
    const view = wrapper.vm as unknown as { load: () => Promise<void> }
    const reload = view.load()
    await flushPromises()
    await wrapper.get('[data-test="create-model"]').trigger('click')
    const drawer = wrapper.getComponent(ModelFormDrawer)
    await drawer.get('[data-test="model-canonical-name"]').setValue('local-model')
    await drawer.get('[data-test="model-display-name"]').setValue('本地模型')
    await drawer.get('[data-test="model-submit"]').trigger('click')
    await flushPromises()
    reloadGate.resolve(undefined)
    await reload
    await flushPromises()

    expect(wrapper.text()).toContain('本地模型')
    expect(wrapper.text()).not.toContain('stale catalog failure')
    wrapper.unmount()
  })

  it('合并过期目录成功中的提供商且不覆盖本地模型和路由数', async () => {
    useCatalog()
    const wrapper = mount(ModelsView, { attachTo: document.body })
    await flushPromises()

    const reloadGate = deferred<undefined>()
    const originalProtocol = providerFixture.protocols[0]
    if (originalProtocol === undefined) throw new Error('缺少测试协议')
    const replacementProvider: ProviderResponse = {
      ...providerFixture,
      id: 12,
      name: '刷新后的提供商',
      protocols: [{ ...originalProtocol, id: 121 }],
    }
    server.use(
      http.get('/admin/models', async () => {
        await reloadGate.promise
        return HttpResponse.json([modelFixture])
      }),
      http.get('/admin/providers', () => HttpResponse.json([replacementProvider])),
      http.get('/admin/model-routes', ({ request }) =>
        HttpResponse.json(new URL(request.url).searchParams.has('model_id') ? [routeFixture] : []),
      ),
      http.post('/admin/models', async ({ request }) => {
        const payload = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          ...modelFixture,
          ...payload,
          id: 3,
          aliases: [],
        })
      }),
    )
    const view = wrapper.vm as unknown as { load: () => Promise<void> }
    const reload = view.load()
    await flushPromises()
    await wrapper.get('[data-test="create-model"]').trigger('click')
    const modelDrawer = wrapper.getComponent(ModelFormDrawer)
    await modelDrawer.get('[data-test="model-canonical-name"]').setValue('local-during-success')
    await modelDrawer.get('[data-test="model-display-name"]').setValue('保留的本地模型')
    await modelDrawer.get('[data-test="model-submit"]').trigger('click')
    await flushPromises()

    reloadGate.resolve(undefined)
    await reload
    await flushPromises()
    expect(wrapper.text()).toContain('保留的本地模型')
    expect(wrapper.get('[data-test="route-count-1"]').text()).toBe('1')
    await wrapper.get('[data-test="create-route-1"]').trigger('click')
    expect(wrapper.getComponent(RouteFormDrawer).text()).toContain('刷新后的提供商')
    wrapper.unmount()
  })
})
