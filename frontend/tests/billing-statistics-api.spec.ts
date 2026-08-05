import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import {
  getAdminBillingStatistics,
  getUserBillingStatistics,
} from '@/api/billingStatistics'

const server = setupServer()

beforeAll(() => { server.listen({ onUnhandledRequest: 'error' }) })
afterEach(() => { server.resetHandlers() })
afterAll(() => { server.close() })

describe('账单统计 API', () => {
  it('以重复查询参数发送管理员的多选筛选条件', async () => {
    server.use(
      http.get('/admin/billing-statistics', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.getAll('provider_ids')).toEqual(['2', '3'])
        expect(url.searchParams.getAll('model_ids')).toEqual(['4'])
        expect(url.searchParams.getAll('api_key_ids')).toEqual(['5', '6'])
        expect(url.searchParams.get('start_at')).toBe('2026-08-01T00:00:00.000Z')
        expect(url.searchParams.get('end_at')).toBe('2026-08-02T00:00:00.000Z')
        return HttpResponse.json({ totals: {}, daily_usage: [], provider_stats: [], model_stats: [], api_key_stats: [] })
      }),
    )

    await getAdminBillingStatistics({
      startAt: '2026-08-01T00:00:00.000Z',
      endAt: '2026-08-02T00:00:00.000Z',
      providerIds: [2, 3],
      modelIds: [4],
      apiKeyIds: [5, 6],
    })
  })

  it('不向普通用户端点泄漏供应商筛选条件', async () => {
    server.use(
      http.get('/user/billing-statistics', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.has('provider_ids')).toBe(false)
        expect(url.searchParams.getAll('model_ids')).toEqual(['4'])
        return HttpResponse.json({ totals: {}, daily_usage: [], model_stats: [], api_key_stats: [] })
      }),
    )

    await getUserBillingStatistics({
      startAt: '2026-08-01T00:00:00.000Z',
      endAt: '2026-08-02T00:00:00.000Z',
      modelIds: [4],
      apiKeyIds: [],
    })
  })
})
