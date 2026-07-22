import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessageBox, type MessageBoxData } from 'element-plus'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import type { ProviderResponse } from '@/api/types'
import ProviderFormDrawer from '@/components/providers/ProviderFormDrawer.vue'
import { routes } from '@/router'
import ProvidersView from '@/views/ProvidersView.vue'

const providerFixture: ProviderResponse = {
  id: 1,
  name: 'OpenAI 主线路',
  has_credential: true,
  enabled: true,
  auto_load_models: true,
  model_sync_interval_seconds: 3600,
  last_model_sync_at: '2026-07-22T08:30:00Z',
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

  it('创建时支持多条协议，并把对象格式凭据与请求头发送到接口', async () => {
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

  it('拒绝数组或标量 JSON，并在对应协议行显示请求头错误', async () => {
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
    await flushPromises()

    expect(wrapper.get('[data-test="credential-error"]').text()).toContain('必须是 JSON 对象')
    expect(wrapper.get('[data-test="protocol-extra-error-0"]').text()).toContain(
      '必须是 JSON 对象',
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
    await flushPromises()

    expect(wrapper.get('[data-test="provider-notice"]').text()).toContain(
      '发现 12 个，新增模型 2 个，新增路由 3 条，更新路由 4 条，停用路由 1 条',
    )
    wrapper.unmount()
  })

  it('供应商已有历史记录时保留列表项并引导改为停用', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({
      value: '',
      action: 'confirm',
    } as MessageBoxData)
    server.use(
      http.delete('/admin/providers/1', () =>
        HttpResponse.json(
          {
            detail: {
              code: 'provider_has_history',
              message: 'Providers with request history must be disabled instead of deleted',
            },
          },
          { status: 409 },
        ),
      ),
    )
    const wrapper = await mountProviders()

    await wrapper.get('[data-test="delete-provider-1"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('OpenAI 主线路')
    expect(wrapper.get('[data-test="provider-notice"]').text()).toContain('请求历史')
    expect(wrapper.get('[data-test="provider-notice"]').text()).toContain('停用')
    wrapper.unmount()
  })
})
