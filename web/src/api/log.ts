import { api } from './index'
import type { LogDetailResponse, LogListResponse, LogFilterOptionsResponse } from '@/types/log'

export const logApi = {
  // List logs with pagination
  list: (params?: {
    page?: number
    page_size?: number
    model?: string
    provider?: string
    status?: string
    start_date?: string
    end_date?: string
  }) =>
    api.get<LogListResponse>('/logs', { params }),

  // Get log detail (returns { log, detail })
  getDetail: (id: number) =>
    api.get<LogDetailResponse>(`/logs/${id}`),

  // Get filter options (distinct models and providers from logs)
  getFilters: () =>
    api.get<LogFilterOptionsResponse>('/logs/filters'),

  // Cleanup log details (admin only)
  cleanup: (days?: number) =>
    api.delete('/logs/cleanup', { params: { days } })
}