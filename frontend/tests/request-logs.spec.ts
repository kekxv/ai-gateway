import { createPinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { listRequestLogs, listUserRequestLogs } from '@/api/requestLogs'
import type {
  ApiKeyResponse,
  CurrentUser,
  ModelResponse,
  ProviderResponse,
  RequestLogDetail,
  RequestLogSummary,
  UserRequestLogSummary,
  UserResponse,
} from '@/api/types'
import JsonViewer from '@/components/common/JsonViewer.vue'
import { routes } from '@/router'
import { useAuthStore } from '@/stores/auth'
import RequestLogsView from '@/views/RequestLogsView.vue'

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

const firstLog: RequestLogSummary = {
  id: '11111111-1111-4111-8111-111111111111',
  user_id: 2,
  user_email: 'audit-member@example.com',
  api_key_id: 31,
  api_key_name: 'Audit Key',
  api_key_prefix: 'sk-gw-audit-',
  model_id: 21,
  model_name: 'audit-model',
  provider_id: 11,
  provider_name: 'audit-provider',
  model_route_id: 201,
  route_upstream_model: 'provider-audit-model',
  inbound_protocol: 'claude',
  outbound_protocol: 'openai',
  transport: 'http',
  stream: true,
  status: 'failed',
  http_status: 502,
  prompt_tokens: 1234,
  completion_tokens: 56,
  cache_read_tokens: 789,
  cache_write_tokens: 123,
  usage_source: 'provider',
  cost: '0.000000019876543210',
  latency_ms: 2430,
  first_token_ms: 315,
  error_code: 'upstream_timeout',
  created_at: '2026-07-22T08:00:00Z',
  completed_at: '2026-07-22T08:00:02Z',
}

const secondLog: RequestLogSummary = {
  ...firstLog,
  id: '22222222-2222-4222-8222-222222222222',
  status: 'completed',
  http_status: 200,
  error_code: null,
  stream: false,
  created_at: '2026-07-22T07:00:00Z',
}

const detail: RequestLogDetail = {
  ...firstLog,
  request_detail: {
    headers: { authorization: '[REDACTED]' },
    body: { prompt: '<script>window.__unsafe = true</script>' },
  },
  response_detail: {
    headers: { 'set-cookie': '[REDACTED]' },
    body: { error: '上游超时' },
  },
}

const adminUser: CurrentUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin',
  is_active: true,
  totp_enabled: false,
  created_at: '2026-07-22T00:00:00',
  updated_at: '2026-07-22T00:00:00',
}

const memberUser: CurrentUser = {
  ...adminUser,
  id: 2,
  email: 'audit-member@example.com',
  role: 'user',
}

const users: UserResponse[] = [
  {
    id: 2,
    email: 'audit-member@example.com',
    role: 'user',
    is_active: true,
    balance: '10.00000000',
    total_spent: '1.00000000',
    created_at: '2026-07-22T00:00:00Z',
    updated_at: '2026-07-22T00:00:00Z',
  },
]

const apiKeys: ApiKeyResponse[] = [
  {
    id: 31,
    user_id: 2,
    name: 'Audit Key',
    key_prefix: 'sk-gw-audit-',
    scope: 'all',
    is_active: true,
    expires_at: null,
    last_used_at: null,
    created_at: '2026-07-22T00:00:00Z',
    provider_ids: [],
    model_ids: [],
  },
]

const models: ModelResponse[] = [
  {
    id: 21,
    canonical_name: 'audit-model',
    display_name: 'Audit Model',
    input_price_per_million: '1.00000000',
    output_price_per_million: '2.00000000',
    cache_read_price_per_million: '0.00000000',
    cache_write_price_per_million: '0.00000000',
    price_multiplier: 1,
    enabled: true,
    aliases: [],
    routing_strategy: 'weighted_random',
    created_at: '2026-07-22T00:00:00Z',
    updated_at: '2026-07-22T00:00:00Z',
  },
]

const providers: ProviderResponse[] = [
  {
    id: 11,
    name: 'audit-provider',
    has_credential: true,
    enabled: true,
    auto_load_models: false,
    model_sync_interval_seconds: 3600,
    last_model_sync_at: null,
    protocols: [],
    cost_multiplier: 1,
    public_multiplier: 1,
  },
]

const userLog: UserRequestLogSummary = {
  id: firstLog.id,
  api_key_id: firstLog.api_key_id,
  api_key_name: firstLog.api_key_name,
  api_key_prefix: firstLog.api_key_prefix,
  model_id: firstLog.model_id,
  model_name: firstLog.model_name,
  inbound_protocol: firstLog.inbound_protocol,
  outbound_protocol: firstLog.outbound_protocol,
  transport: firstLog.transport,
  stream: firstLog.stream,
  status: firstLog.status,
  http_status: firstLog.http_status,
  prompt_tokens: firstLog.prompt_tokens,
  completion_tokens: firstLog.completion_tokens,
  cache_read_tokens: firstLog.cache_read_tokens,
  cache_write_tokens: firstLog.cache_write_tokens,
  usage_source: firstLog.usage_source,
  cost: firstLog.cost,
  latency_ms: firstLog.latency_ms,
  first_token_ms: firstLog.first_token_ms,
  error_code: firstLog.error_code,
  created_at: firstLog.created_at,
  completed_at: firstLog.completed_at,
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

function useLogs(items: RequestLogSummary[] = [firstLog], nextCursor: string | null = null): void {
  server.use(
    http.get('/admin/request-logs', () =>
      HttpResponse.json({ items, next_cursor: nextCursor }),
    ),
    http.get('/admin/request-logs/:requestId', () => HttpResponse.json(detail)),
  )
}

function useAdminCatalogs(): void {
  server.use(
    http.get('/admin/users', () => HttpResponse.json(users)),
    http.get('/admin/api-keys', () => HttpResponse.json(apiKeys)),
    http.get('/admin/models', () => HttpResponse.json(models)),
    http.get('/admin/providers', () => HttpResponse.json(providers)),
  )
}

function useUserCatalogs(): void {
  server.use(
    http.get('/user/api-keys', () => HttpResponse.json(apiKeys)),
    http.get('/user/models', () => HttpResponse.json(models)),
  )
}

function mountRequestLogs(user: CurrentUser = adminUser) {
  if (user.role === 'admin') useAdminCatalogs()
  else useUserCatalogs()
  const pinia = createPinia()
  const auth = useAuthStore(pinia)
  auth.user = user
  auth.ready = true
  return mount(RequestLogsView, {
    attachTo: document.body,
    global: { plugins: [pinia] },
  })
}

async function mountLogs(
  items: RequestLogSummary[] = [firstLog],
  nextCursor: string | null = null,
): Promise<VueWrapper> {
  useLogs(items, nextCursor)
  const wrapper = mountRequestLogs()
  await flushPromises()
  return wrapper
}

describe('请求日志搜索与详情检查', () => {
  it('通过本地懒加载路由提供请求日志页面', async () => {
    const shellRoute = routes.find((route) => route.path === '/')
    const logRoute = shellRoute?.children?.find((route) => route.name === 'request-logs')
    if (typeof logRoute?.component !== 'function') throw new Error('请求日志路由不是懒加载组件')

    const loadRequestLogs = logRoute.component as () => Promise<{ default: unknown }>
    const loadedModule = await loadRequestLogs()
    expect(loadedModule.default).toBe(RequestLogsView)
  })

  it('序列化全部受支持过滤项、ISO 本地时间、cursor 和 page size，并省略空值', async () => {
    const requests: URL[] = []
    server.use(
      http.get('/admin/request-logs', ({ request }) => {
        requests.push(new URL(request.url))
        return HttpResponse.json({ items: [], next_cursor: null })
      }),
    )

    await listRequestLogs({
      requestId: ' 11111111-1111-4111-8111-111111111111 ',
      userId: 2,
      apiKeyId: 31,
      modelId: 21,
      providerId: 11,
      status: 'failed',
      protocol: 'claude',
      createdFrom: '2026-07-21T08:30',
      createdTo: '2026-07-22T09:45',
      cursor: 'next-page-token',
      pageSize: 25,
    })
    await listRequestLogs({ requestId: '  ' })

    const params = requests[0]?.searchParams
    expect(Object.fromEntries(params?.entries() ?? [])).toEqual({
      request_id: '11111111-1111-4111-8111-111111111111',
      user_id: '2',
      api_key_id: '31',
      model_id: '21',
      provider_id: '11',
      status: 'failed',
      protocol: 'claude',
      created_from: new Date('2026-07-21T08:30').toISOString(),
      created_to: new Date('2026-07-22T09:45').toISOString(),
      cursor: 'next-page-token',
      page_size: '25',
    })
    expect(requests[1]?.search).toBe('')
  })

  it('普通用户查询不会序列化供应商过滤条件', async () => {
    const requests: URL[] = []
    server.use(
      http.get('/user/request-logs', ({ request }) => {
        requests.push(new URL(request.url))
        return HttpResponse.json({ items: [], next_cursor: null })
      }),
    )

    await listUserRequestLogs({ apiKeyId: 31, modelId: 21, providerId: 11 })

    expect(Object.fromEntries(requests[0]?.searchParams.entries() ?? [])).toEqual({
      api_key_id: '31',
      model_id: '21',
    })
  })

  it('使用后端 cursor 前后翻页，不推断总页数', async () => {
    const requests: URL[] = []
    server.use(
      http.get('/admin/request-logs', ({ request }) => {
        const url = new URL(request.url)
        requests.push(url)
        return url.searchParams.get('cursor') === 'page-two'
          ? HttpResponse.json({ items: [secondLog], next_cursor: null })
          : HttpResponse.json({ items: [firstLog], next_cursor: 'page-two' })
      }),
    )
    const wrapper = mountRequestLogs()
    await flushPromises()

    expect(wrapper.find(`[data-test="request-log-${firstLog.id}"]`).exists()).toBe(true)
    expect(wrapper.get('[data-test="logs-next"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-test="logs-next"]').trigger('click')
    await flushPromises()
    expect(requests.at(-1)?.searchParams.get('cursor')).toBe('page-two')
    expect(wrapper.find(`[data-test="request-log-${secondLog.id}"]`).exists()).toBe(true)
    expect(wrapper.get('[data-test="logs-next"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-test="logs-previous"]').trigger('click')
    await flushPromises()
    expect(requests.at(-1)?.searchParams.has('cursor')).toBe(false)
    expect(wrapper.find(`[data-test="request-log-${firstLog.id}"]`).exists()).toBe(true)
    wrapper.unmount()
  })

  it('使用友好实体下拉框发送内部 ID，并重置 cursor 栈和当前页起点', async () => {
    const requests: URL[] = []
    server.use(
      http.get('/admin/request-logs', ({ request }) => {
        requests.push(new URL(request.url))
        return HttpResponse.json({ items: [firstLog], next_cursor: 'page-two' })
      }),
    )
    const wrapper = mountRequestLogs()
    await flushPromises()
    expect(wrapper.get('[data-test="log-user-id"]').text()).toContain('audit-member@example.com')
    expect(wrapper.get('[data-test="log-api-key-id"]').text()).toContain('Audit Key')
    expect(wrapper.get('[data-test="log-model-id"]').text()).toContain('Audit Model')
    expect(wrapper.get('[data-test="log-provider-id"]').text()).toContain('audit-provider')
    await wrapper.get('[data-test="logs-next"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-test="log-status"]').setValue('failed')
    await wrapper.get('[data-test="log-protocol"]').setValue('claude')
    await wrapper.get('[data-test="log-user-id"]').setValue('2')
    await wrapper.get('[data-test="log-api-key-id"]').setValue('31')
    await wrapper.get('[data-test="log-model-id"]').setValue('21')
    await wrapper.get('[data-test="log-provider-id"]').setValue('11')
    await flushPromises()

    const lastRequest = requests.at(-1)
    expect(lastRequest?.searchParams.get('status')).toBe('failed')
    expect(lastRequest?.searchParams.get('protocol')).toBe('claude')
    expect(lastRequest?.searchParams.get('user_id')).toBe('2')
    expect(lastRequest?.searchParams.get('api_key_id')).toBe('31')
    expect(lastRequest?.searchParams.get('model_id')).toBe('21')
    expect(lastRequest?.searchParams.get('provider_id')).toBe('11')
    expect(lastRequest?.searchParams.has('cursor')).toBe(false)
    const exposed = wrapper.vm as unknown as { cursorStack: Array<string | null> }
    expect(exposed.cursorStack).toEqual([])
    wrapper.unmount()
  })

  it('隐藏请求 UUID 并展示可读实体、用量和精确费用', async () => {
    const wrapper = await mountLogs()

    for (const heading of [
      '用户 / 密钥', '模型 / 供应商 / 上游模型', '请求信息',
      '令牌', '用户费用 / 成本费用', '延迟 / 首个令牌',
      '错误代码', '创建时间',
    ]) {
      expect(wrapper.text()).toContain(heading)
    }
    expect(wrapper.get('.log-table thead').text()).not.toContain('请求 ID')
    const row = wrapper.get(`[data-test="request-log-${firstLog.id}"]`)
    expect(row.text()).not.toContain(firstLog.id)
    expect(row.text()).not.toContain('用户 #2')
    expect(row.text()).not.toContain('模型 #21')
    expect(row.text()).toContain('audit-member@example.com')
    expect(row.text()).toContain('Audit Key')
    expect(row.text()).not.toContain('sk-gw-audit-…')
    expect(row.text()).toContain('audit-model')
    expect(row.text()).toContain('audit-provider')
    expect(row.text()).toContain('provider-audit-model')
    expect(row.text()).toContain('Claude → OpenAI')
    expect(row.text()).toContain('HTTP')
    expect(row.text()).toContain('流式')
    expect(row.text()).toContain('失败')
    expect(row.text()).toContain('HTTP 502')
    expect(row.text()).toContain(`¥${firstLog.cost}`)
    expect(row.text()).toContain('1234 / 56')
    expect(row.text()).toContain('缓存 789 / 123')
    wrapper.unmount()
  })

  it('普通用户只加载有权限的筛选项，列表和详情均不显示供应商信息', async () => {
    let providerRequests = 0
    server.use(
      http.get('/admin/providers', () => {
        providerRequests += 1
        return HttpResponse.json(providers)
      }),
      http.get('/user/request-logs', () =>
        HttpResponse.json({ items: [userLog], next_cursor: null }),
      ),
      http.get('/user/request-logs/:requestId', () => HttpResponse.json(userLog)),
    )

    const wrapper = mountRequestLogs(memberUser)
    await flushPromises()

    expect(providerRequests).toBe(0)
    expect(wrapper.find('[data-test="log-user-id"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="log-provider-id"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="log-api-key-id"]').text()).toContain('Audit Key')
    expect(wrapper.get('[data-test="log-model-id"]').text()).toContain('Audit Model')
    const row = wrapper.get(`[data-test="request-log-${userLog.id}"]`)
    expect(row.text()).toContain('audit-model')
    expect(row.text()).not.toContain('audit-provider')
    expect(row.text()).not.toContain('provider-audit-model')

    await wrapper.get(`[data-test="inspect-log-${userLog.id}"]`).trigger('click')
    await flushPromises()
    expect(document.body.textContent).not.toContain('供应商 / 上游模型')
    expect(document.body.textContent).not.toContain('audit-provider')
    expect(document.body.textContent).not.toContain('provider-audit-model')
    wrapper.unmount()
  })

  it('仅在打开抽屉后加载详情，并用 escaped pre 展示服务端脱敏 JSON', async () => {
    let detailCalls = 0
    server.use(
      http.get('/admin/request-logs', () =>
        HttpResponse.json({ items: [firstLog], next_cursor: null }),
      ),
      http.get('/admin/request-logs/:requestId', () => {
        detailCalls += 1
        return HttpResponse.json(detail)
      }),
    )
    const wrapper = mountRequestLogs()
    await flushPromises()
    expect(detailCalls).toBe(0)

    await wrapper.get(`[data-test="inspect-log-${firstLog.id}"]`).trigger('click')
    await flushPromises()

    expect(detailCalls).toBe(1)
    expect(document.body.textContent).toContain('敏感字段已由服务端脱敏')
    expect(document.body.textContent).toContain('[REDACTED]')
    expect(document.body.textContent).toContain('缓存读取 / 写入令牌')
    expect(document.body.textContent).toContain('789 / 123')
    expect(document.body.textContent).toContain('<script>window.__unsafe = true</script>')
    expect(document.body.querySelector('script')).toBeNull()
    const requestDetails = document.body.querySelector('[data-test="request-json-section"]')
    expect(requestDetails?.hasAttribute('open')).toBe(false)
    expect(requestDetails?.querySelector('pre')).not.toBeNull()
    wrapper.unmount()
  })

  it('JsonViewer 提供换行 JSON 和复制按钮而不把内容写入通知', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    const wrapper = mount(JsonViewer, {
      props: { title: '请求 JSON', value: { authorization: '[REDACTED]', nested: { ok: true } } },
    })

    expect(wrapper.get('pre').text()).toContain('\n  "authorization": "[REDACTED]"')
    await wrapper.get('[data-test="copy-json"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith(
      '{\n  "authorization": "[REDACTED]",\n  "nested": {\n    "ok": true\n  }\n}',
    )
    expect(wrapper.text()).toContain('已复制')
    wrapper.unmount()
  })

  it('过滤变化中止旧列表并防止陈旧响应覆盖最新会话', async () => {
    const stale = deferred<Response>()
    const abortSpy = vi
      .spyOn(AbortController.prototype, 'abort')
      .mockImplementation(() => undefined)
    let calls = 0
    server.use(
      http.get('/admin/request-logs', ({ request }) => {
        calls += 1
        if (calls === 1) return HttpResponse.json({ items: [firstLog], next_cursor: null })
        if (new URL(request.url).searchParams.get('user_id') === '2') return stale.promise
        return HttpResponse.json({ items: [secondLog], next_cursor: null })
      }),
    )
    const wrapper = mountRequestLogs()
    await flushPromises()

    await wrapper.get('[data-test="log-user-id"]').setValue('2')
    await wrapper.get('[data-test="log-user-id"]').setValue('')
    await flushPromises()
    expect(wrapper.find(`[data-test="request-log-${secondLog.id}"]`).exists()).toBe(true)
    expect(abortSpy).toHaveBeenCalled()

    stale.resolve(HttpResponse.json({ items: [firstLog], next_cursor: null }))
    await flushPromises()
    expect(wrapper.find(`[data-test="request-log-${secondLog.id}"]`).exists()).toBe(true)
    expect(wrapper.find(`[data-test="request-log-${firstLog.id}"]`).exists()).toBe(false)
    wrapper.unmount()
  })

  it('卸载时中止列表和详情请求，迟到的详情不会进入 DOM', async () => {
    const detailGate = deferred<Response>()
    const abortSpy = vi.spyOn(AbortController.prototype, 'abort')
    server.use(
      http.get('/admin/request-logs', () =>
        HttpResponse.json({ items: [firstLog], next_cursor: null }),
      ),
      http.get('/admin/request-logs/:requestId', () => detailGate.promise),
    )
    const wrapper = mountRequestLogs()
    await flushPromises()
    await wrapper.get(`[data-test="inspect-log-${firstLog.id}"]`).trigger('click')
    await flushPromises()

    wrapper.unmount()
    detailGate.resolve(HttpResponse.json(detail))
    await flushPromises()
    expect(abortSpy).toHaveBeenCalled()
    expect(document.body.textContent).not.toContain('<script>window.__unsafe = true</script>')
  })
})
