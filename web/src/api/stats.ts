import { api } from './index'
import type { Stats } from '@/types/stats'

interface StatsQueryParams {
  start_date?: string
  end_date?: string
}

export const statsApi = {
  // Get dashboard stats
  getStats: (params?: StatsQueryParams) =>
    api.get<Stats>('/stats', { params }),

  // Test model
  testModel: (data: { providerId: number; model: string; prompt: string }) =>
    api.post('/test-model', data)
}