import { defineComponent } from 'vue'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import * as dashboardApi from '@/api/dashboard'
import type { CurrentUser, DashboardSummary } from '@/api/types'
import { routes } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { formatDuration, formatInteger, formatMoney, formatPercent } from '@/utils/format'
import DashboardView from '@/views/DashboardView.vue'

vi.mock('vue-echarts', () => ({
  default: defineComponent({
    name: 'VChartStub',
    props: {
      autoresize: { type: [Boolean, Object], default: false },
      option: { type: Object, required: true },
    },
    template: '<div class="v-chart-stub" />',
  }),
}))

const summaryFixture: DashboardSummary = {
  users_total: 12_345,
  active_api_keys: 98,
  providers: { total: 3, enabled: 2 },
  models: { total: 8, enabled: 7 },
  routes: { total: 6, enabled: 5, unavailable: 1 },
  requests_24h: 1_234,
  failed_requests_24h: 25,
  prompt_tokens_24h: 456_789,
  completion_tokens_24h: 123_456,
  cost_24h: '0.125',
  cost_amount_24h: '0.100',
  gross_profit_24h: '0.025',
  average_latency_ms_24h: 248,
  daily_usage: [
    { date: '2026-07-16', requests: 40, failures: 2, cost: '0.01000000' },
    { date: '2026-07-17', requests: 48, failures: 1, cost: '0.02000000' },
    { date: '2026-07-18', requests: 52, failures: 3, cost: '0.03000000' },
    { date: '2026-07-19', requests: 60, failures: 0, cost: '0.04000000' },
    { date: '2026-07-20', requests: 55, failures: 1, cost: '0.05000000' },
    { date: '2026-07-21', requests: 70, failures: 2, cost: '0.06000000' },
    { date: '2026-07-22', requests: 80, failures: 4, cost: '0.07000000' },
  ],
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

const zeroSummary: DashboardSummary = {
  ...summaryFixture,
  requests_24h: 0,
  failed_requests_24h: 0,
  prompt_tokens_24h: 0,
  completion_tokens_24h: 0,
  cost_24h: '0E-8',
  average_latency_ms_24h: null,
  daily_usage: summaryFixture.daily_usage.map((point) => ({
    ...point,
    requests: 0,
    failures: 0,
    cost: '-0E-8',
  })),
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

function mountDashboard() {
  const pinia = createPinia()
  const auth = useAuthStore(pinia)
  auth.user = adminUser
  auth.ready = true
  return mount(DashboardView, {
    global: { plugins: [pinia] },
  })
}

describe('控制台概览', () => {
  it('通过独立懒加载路由提供概览页面', async () => {
    const shellRoute = routes.find((route) => route.path === '/')
    const dashboardRoute = shellRoute?.children?.find((route) => route.name === 'dashboard')
    if (typeof dashboardRoute?.component !== 'function') {
      throw new Error('控制台概览路由不是懒加载组件')
    }

    const loadDashboard = dashboardRoute.component as () => Promise<{ default: unknown }>
    const loadedModule = await loadDashboard()
    expect(loadedModule.default).toBe(DashboardView)
  })

  it('渲染资源、24 小时指标、精确金额与熔断路由告警', async () => {
    const exactSummary: DashboardSummary = {
      ...summaryFixture,
      daily_usage: summaryFixture.daily_usage.map((point, index) => ({
        ...point,
        cost:
          index === 0
            ? '9007199254740993.12345678'
            : index === 1
              ? '1E-8'
              : point.cost,
      })),
    }
    server.use(
      http.get('/admin/dashboard/summary', () => HttpResponse.json(exactSummary)),
    )

    const wrapper = mountDashboard()
    await flushPromises()

    expect(wrapper.text()).toContain('用户总数 12,345')
    expect(wrapper.text()).toContain('活跃接口密钥 98')
    expect(wrapper.text()).toContain('启用提供商 2 / 3')
    expect(wrapper.text()).toContain('启用模型 7 / 8')
    expect(wrapper.text()).toContain('启用路由 5 / 6')
    expect(wrapper.text()).toContain('24 小时请求 1,234')
    expect(wrapper.text()).toContain('失败率 2.0%')
    expect(wrapper.text()).toContain('24 小时费用 ¥0.12500000')
    expect(wrapper.text()).toContain('1 条路由处于熔断状态')
    expect(wrapper.get('.el-alert').text()).toContain('1 条路由处于熔断状态')

    const chart = wrapper.getComponent({ name: 'VChartStub' })
    expect(chart.props('autoresize')).toBe(true)
    expect(chart.attributes('aria-label')).toBeUndefined()
    expect(chart.attributes('aria-hidden')).toBe('true')
    const option = chart.props('option') as {
      aria: {
        decal?: { show?: boolean }
        description?: string
        enabled?: boolean
        label?: { enabled?: boolean }
      }
      series: Array<{ data: unknown[]; type: string; yAxisIndex?: number }>
      yAxis: unknown[]
    }
    expect(option.aria.enabled).toBe(true)
    expect(option.aria.label?.enabled).toBe(false)
    expect(option.aria.decal?.show).toBe(true)
    expect(option.aria.description).toBeUndefined()
    expect(option.yAxis).toHaveLength(2)
    expect(option.series.map((series) => series.type)).toEqual(['bar', 'bar', 'line'])
    expect(option.series[2]?.yAxisIndex).toBe(1)
    expect(option.series[2]?.data).toEqual(exactSummary.daily_usage.map(({ cost }) => cost))

    const tooltip = (chart.props('option') as {
      tooltip: {
        formatter: (params: Array<{ dataIndex: number; value: number }>) => string
      }
    }).tooltip.formatter
    expect(tooltip([{ dataIndex: 0, value: 9_007_199_254_740_994 }])).toContain(
      '¥9007199254740993.12345678',
    )
    expect(tooltip([{ dataIndex: 1, value: 0.00000001 }])).toContain('¥0.00000001')

    const accessibleTable = wrapper.get('[data-test="daily-usage-table"]')
    expect(accessibleTable.attributes('aria-hidden')).toBeUndefined()
    expect(accessibleTable.classes()).toContain('visually-hidden')
    expect(accessibleTable.get('caption').text()).toBe('近 7 天每日请求、失败与费用明细')
    const accessibleRows = accessibleTable.findAll('tbody tr')
    expect(accessibleRows).toHaveLength(7)
    exactSummary.daily_usage.forEach((point, index) => {
      const rowText = accessibleRows[index]?.text() ?? ''
      expect(rowText).toContain(point.date)
      expect(rowText).toContain(String(point.requests))
      expect(rowText).toContain(String(point.failures))
      expect(rowText).toContain(formatMoney(point.cost))
    })

    wrapper.unmount()
  })

  it('首次请求显示骨架屏，并把七日全零数据作为有效空状态', async () => {
    let releaseRequest!: () => void
    server.use(
      http.get('/admin/dashboard/summary', async () => {
        await new Promise<void>((resolve) => {
          releaseRequest = resolve
        })
        return HttpResponse.json(zeroSummary)
      }),
    )

    const wrapper = mountDashboard()
    await vi.waitFor(() => {
      expect(wrapper.find('[data-test="dashboard-skeleton"]').exists()).toBe(true)
      expect(releaseRequest).toBeTypeOf('function')
    })

    releaseRequest()
    await flushPromises()

    expect(wrapper.get('[data-test="chart-empty"]').text()).toContain(
      '近 7 天暂无请求与费用数据',
    )
    expect(wrapper.findComponent({ name: 'VChartStub' }).exists()).toBe(false)
    expect(wrapper.text()).toContain('24 小时费用 ¥0.00000000')
    expect(wrapper.text()).toContain('平均延迟 —')

    wrapper.unmount()
  })

  it('请求失败时显示可重试结果面板，并在重试成功后恢复概览', async () => {
    let attempts = 0
    server.use(
      http.get('/admin/dashboard/summary', () => {
        attempts += 1
        if (attempts === 1) {
          return HttpResponse.json(
            { detail: { code: 'dashboard_unavailable', message: 'internal details' } },
            { status: 503 },
          )
        }
        return HttpResponse.json(summaryFixture)
      }),
    )

    const wrapper = mountDashboard()
    await flushPromises()

    expect(wrapper.get('[data-test="dashboard-error"]').text()).toContain(
      '概览数据加载失败',
    )
    expect(wrapper.text()).not.toContain('internal details')

    await wrapper.get('[data-test="dashboard-retry"]').trigger('click')
    await flushPromises()

    expect(attempts).toBe(2)
    expect(wrapper.find('[data-test="dashboard-error"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('24 小时费用 ¥0.12500000')

    wrapper.unmount()
  })

  it('快速重试时取消旧请求，且只渲染最新响应', async () => {
    const latestSummary: DashboardSummary = {
      ...summaryFixture,
      cost_24h: '2.00000000',
    }
    const signals: Array<AbortSignal | undefined> = []
    let releaseSecond!: () => void
    let attempts = 0
    vi.spyOn(dashboardApi, 'getDashboardSummary').mockImplementation((signal) => {
      signals.push(signal)
      attempts += 1
      if (attempts === 1) return Promise.reject(new Error('暂时失败'))
      if (attempts === 2) {
        return new Promise<DashboardSummary>((resolve) => {
          releaseSecond = () => {
            resolve({ ...summaryFixture, cost_24h: '1.00000000' })
          }
        })
      }
      return Promise.resolve(latestSummary)
    })

    const wrapper = mountDashboard()
    await flushPromises()
    const loadSummary = (
      wrapper.vm as unknown as {
        $: { setupState: { loadSummary: () => Promise<void> } }
      }
    ).$.setupState.loadSummary
    void loadSummary()
    await vi.waitFor(() => {
      expect(attempts).toBe(2)
      expect(releaseSecond).toBeTypeOf('function')
    })

    await loadSummary()
    await vi.waitFor(() => {
      expect(attempts).toBe(3)
      expect(signals[1]?.aborted).toBe(true)
    })
    releaseSecond()
    await flushPromises()

    expect(wrapper.text()).toContain('24 小时费用 ¥2.00000000')
    expect(wrapper.text()).not.toContain('24 小时费用 ¥1.00000000')
    wrapper.unmount()
  })

  it('组件卸载时取消尚未完成的概览请求', async () => {
    let activeSignal: AbortSignal | undefined
    vi.spyOn(dashboardApi, 'getDashboardSummary').mockImplementation((signal) => {
      activeSignal = signal
      return new Promise<DashboardSummary>(() => {})
    })

    const wrapper = mountDashboard()
    await vi.waitFor(() => {
      expect(activeSignal).toBeDefined()
    })
    expect(activeSignal?.aborted).toBe(false)

    wrapper.unmount()

    await vi.waitFor(() => {
      expect(activeSignal?.aborted).toBe(true)
    })
  })
})

describe('控制台格式化工具', () => {
  it('仅通过字符串精确格式化普通与科学计数金额', () => {
    expect(formatMoney('0.125')).toBe('¥0.12500000')
    expect(formatMoney('9007199254740993.1')).toBe('¥9007199254740993.10000000')
    expect(formatMoney('-12')).toBe('¥-12.00000000')
    expect(formatMoney('+12.5')).toBe('¥+12.50000000')
    expect(formatMoney('1E-8')).toBe('¥0.00000001')
    expect(formatMoney('0E-8')).toBe('¥0.00000000')
    expect(formatMoney('-0E-8')).toBe('¥0.00000000')
    expect(formatMoney('-1.25E+3')).toBe('¥-1250.00000000')
    expect(formatMoney('9.00719925474099312345678E+15')).toBe(
      '¥9007199254740993.12345678',
    )
  })

  it('格式化整数、时长与零分母百分比', () => {
    expect(formatInteger(12_345)).toBe('12,345')
    expect(formatDuration(248)).toBe('248 毫秒')
    expect(formatDuration(null)).toBe('—')
    expect(formatPercent(25, 1_234)).toBe('2.0%')
    expect(formatPercent(0, 0)).toBe('0.0%')
  })
})
