import { apiClient } from './client'
import type { DashboardSummary } from './types'

export async function getDashboardSummary(signal?: AbortSignal): Promise<DashboardSummary> {
  const config = signal === undefined ? undefined : { signal }
  const { data } = await apiClient.get<DashboardSummary>('/admin/dashboard/summary', config)
  return data
}
