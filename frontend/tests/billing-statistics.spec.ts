import { defineComponent } from 'vue'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as statisticsApi from '@/api/billingStatistics'
import type {
  AdminBillingStatisticsResponse,
  CurrentUser,
  UserBillingStatisticsResponse,
} from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import BillingStatisticsView from '@/views/BillingStatisticsView.vue'

vi.mock('vue-echarts', () => ({
  default: defineComponent({
    name: 'VChartStub',
    props: { option: { type: Object, required: true } },
    template: '<div class="v-chart-stub" />',
  }),
}))

vi.mock('@/api/providers', () => ({ listProviders: () => Promise.resolve([{ id: 1, name: '供应商 A' }]) }))
vi.mock('@/api/models', () => ({
  listModels: () => Promise.resolve([{ id: 2, display_name: '模型 A', canonical_name: 'model-a' }]),
  listAvailableModels: () => Promise.resolve([{ id: 2, display_name: '模型 A', canonical_name: 'model-a' }]),
}))
vi.mock('@/api/apiKeys', () => ({
  listApiKeys: () => Promise.resolve([{ id: 3, name: '管理密钥', user_email: 'hidden@example.com' }]),
  listOwnApiKeys: () => Promise.resolve([{ id: 4, name: '我的密钥', user_email: 'hidden@example.com' }]),
}))

const regularUser: CurrentUser = {
  id: 2,
  email: 'member@example.com',
  role: 'user',
  is_active: true,
  totp_enabled: false,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
}

const userResponse: UserBillingStatisticsResponse = {
  totals: {
    requests: 10, failed_requests: 1, prompt_tokens: 100, completion_tokens: 20,
    cache_read_tokens: 5, cache_write_tokens: 1, user_cost: '1.25000000', average_latency_ms: 120,
  },
  daily_usage: [{
    date: '2026-08-01', requests: 10, failed_requests: 1, prompt_tokens: 100,
    completion_tokens: 20, cache_read_tokens: 5, cache_write_tokens: 1,
    user_cost: '1.25000000', average_latency_ms: 120,
  }],
  model_stats: [{
    id: 2, name: '模型 A', requests: 10, failed_requests: 1, prompt_tokens: 100,
    completion_tokens: 20, cache_read_tokens: 5, cache_write_tokens: 1,
    user_cost: '1.25000000', average_latency_ms: 120,
  }],
  api_key_stats: [{
    id: 4, name: '我的密钥', requests: 10, failed_requests: 1, prompt_tokens: 100,
    completion_tokens: 20, cache_read_tokens: 5, cache_write_tokens: 1,
    user_cost: '1.25000000', average_latency_ms: 120,
  }],
}

const adminResponse: AdminBillingStatisticsResponse = {
  ...userResponse,
  totals: { ...userResponse.totals, cost_amount: '0.80000000', gross_profit: '0.45000000' },
  daily_usage: userResponse.daily_usage.map((point) => ({
    ...point, cost_amount: '0.80000000', gross_profit: '0.45000000',
  })),
  model_stats: userResponse.model_stats.map((stat) => ({
    ...stat, cost_amount: '0.80000000', gross_profit: '0.45000000',
  })),
  api_key_stats: userResponse.api_key_stats.map((stat) => ({
    ...stat, cost_amount: '0.80000000', gross_profit: '0.45000000',
  })),
  provider_stats: userResponse.model_stats.map((stat) => ({
    ...stat, id: 1, name: '供应商 A', cost_amount: '0.80000000', gross_profit: '0.45000000',
  })),
}

function mountPage(user: CurrentUser) {
  const pinia = createPinia()
  const auth = useAuthStore(pinia)
  auth.user = user
  auth.ready = true
  return mount(BillingStatisticsView, { global: { plugins: [pinia] } })
}

afterEach(() => vi.restoreAllMocks())

describe('账单统计', () => {
  it('普通用户仅加载自己的统计，隐藏供应商与内部财务，并且密钥不显示邮箱或 ID', async () => {
    const userRequest = vi.spyOn(statisticsApi, 'getUserBillingStatistics').mockResolvedValue(userResponse)
    const adminRequest = vi.spyOn(statisticsApi, 'getAdminBillingStatistics').mockResolvedValue(adminResponse)
    const wrapper = mountPage(regularUser)
    await flushPromises()

    expect(userRequest).toHaveBeenCalledOnce()
    expect(adminRequest).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('用户费用')
    expect(wrapper.text()).not.toContain('内部成本')
    expect(wrapper.text()).not.toContain('毛利')
    expect(wrapper.text()).not.toContain('供应商分布')
    expect(wrapper.findAllComponents({ name: 'ElOption' }).map((option) => String(option.props('label')))).toContain('我的密钥')
    expect(wrapper.text()).not.toContain('hidden@example.com')
    expect(wrapper.text()).not.toContain('#4')
    expect(wrapper.findAllComponents({ name: 'VChartStub' })).toHaveLength(3)
  })

  it('管理员展示供应商、内部成本和毛利，API Key 标签仅显示名称与 ID', async () => {
    vi.spyOn(statisticsApi, 'getUserBillingStatistics').mockResolvedValue(userResponse)
    const adminRequest = vi.spyOn(statisticsApi, 'getAdminBillingStatistics').mockResolvedValue(adminResponse)
    const wrapper = mountPage({ ...regularUser, role: 'admin' })
    await flushPromises()

    expect(adminRequest).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('内部成本')
    expect(wrapper.text()).toContain('毛利')
    expect(wrapper.text()).toContain('供应商分布')
    expect(wrapper.findAllComponents({ name: 'ElOption' }).map((option) => String(option.props('label')))).toContain('管理密钥 · #3')
    expect(wrapper.text()).not.toContain('hidden@example.com')
    expect(wrapper.findAllComponents({ name: 'VChartStub' })).toHaveLength(4)
  })

  it('将时间范围与次要筛选条件分组，并能用七天快捷范围重新查询', async () => {
    const adminRequest = vi.spyOn(statisticsApi, 'getAdminBillingStatistics').mockResolvedValue(adminResponse)
    const wrapper = mountPage({ ...regularUser, role: 'admin' })
    await flushPromises()

    const dateRange = wrapper.get('[data-test="billing-date-range"]')
    const secondaryFilters = wrapper.get('[data-test="billing-secondary-filters"]')
    expect(dateRange.find('[data-test="billing-quick-range-today"]').exists()).toBe(true)
    expect(dateRange.find('[data-test="billing-quick-range-7d"]').exists()).toBe(true)
    expect(dateRange.find('[data-test="billing-quick-range-30d"]').exists()).toBe(true)
    expect(secondaryFilters.find('[data-test="provider-filter"]').exists()).toBe(true)
    expect(secondaryFilters.find('[data-test="model-filter"]').exists()).toBe(true)
    expect(secondaryFilters.find('[data-test="api-key-filter"]').exists()).toBe(true)

    await wrapper.get('[data-test="billing-quick-range-7d"]').trigger('click')
    await flushPromises()

    expect(adminRequest).toHaveBeenCalledTimes(2)
    const query = adminRequest.mock.calls[1]?.[0]
    expect(query).toBeDefined()
    expect(new Date(query?.startAt ?? '').getTime()).toBeLessThan(new Date(query?.endAt ?? '').getTime())
  })
})
