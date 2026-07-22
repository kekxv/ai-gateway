import { flushPromises, mount } from '@vue/test-utils'
import { ElMessageBox, type MessageBoxData } from 'element-plus'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import type { ModelResponse, ModelRouteResponse, ProviderResponse } from '@/api/types'
import ModelFormDrawer from '@/components/models/ModelFormDrawer.vue'
import { routes } from '@/router'
import ModelsView from '@/views/ModelsView.vue'

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
  protocols: [
    {
      id: 111,
      protocol: 'openai',
      base_url: 'https://api.example.com/v1',
      websocket_url: null,
      has_extra_headers: false,
      enabled: true,
    },
  ],
}

const routeFixture: ModelRouteResponse = {
  id: 201,
  model_id: 1,
  provider_id: 11,
  provider_protocol_id: 111,
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

function useCatalog(
  models: ModelResponse[] = [modelFixture],
  modelRoutes: ModelRouteResponse[] = [routeFixture],
): void {
  server.use(
    http.get('/admin/models', () => HttpResponse.json(models)),
    http.get('/admin/providers', () => HttpResponse.json([providerFixture])),
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
    await wrapper.get('[data-test="add-model-alias"]').trigger('click')
    await wrapper.get('[data-test="model-alias-0"]').setValue('fast-chat')
    await wrapper.get('[data-test="model-alias-enabled-0"]').trigger('click')
    await wrapper.get('[data-test="model-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({
      canonical_name: 'gpt-4.1',
      display_name: 'GPT 4.1',
      input_price_per_million: '2.00000000',
      output_price_per_million: '8.00000000',
      enabled: true,
      aliases: [{ alias: 'fast-chat', enabled: false }],
      routing_strategy: 'weighted_random',
    })
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
    await wrapper.get('[data-test="model-display-name"]').setValue('免费模型')
    await wrapper.get('[data-test="model-submit"]').trigger('click')

    expect(onSubmit).toHaveBeenCalledWith({ display_name: '免费模型' })
    wrapper.unmount()
  })

  it('拒绝重复别名和与规范名称相同的别名，并聚焦第一条错误', async () => {
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
    await firstAlias.setValue('gpt-4.1')
    await wrapper.get('[data-test="model-alias-1"]').setValue('gpt-4.1')
    await wrapper.get('[data-test="model-submit"]').trigger('click')
    await waitForFormErrors()

    expect(wrapper.get('[data-validation="model-alias-0"] .el-form-item__error').text()).toContain(
      '不能与规范名称相同',
    )
    expect(wrapper.get('[data-validation="model-alias-1"] .el-form-item__error').text()).toContain(
      '别名不能重复',
    )
    expect(document.activeElement).toBe(firstAlias.element)
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
})
