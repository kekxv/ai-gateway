import { apiClient } from './client'
import type { DashboardSummary, UserDashboardSummary } from './types'

export async function getDashboardSummary(signal?: AbortSignal): Promise<DashboardSummary> {
  const config = signal === undefined ? undefined : { signal }
  const { data } = await apiClient.get<DashboardSummary>('/admin/dashboard/summary', config)
  return data
}

export async function getUserDashboardSummary(signal?: AbortSignal): Promise<UserDashboardSummary> {
  const config = signal === undefined ? undefined : { signal }
  const { data } = await apiClient.get<UserDashboardSummary>('/me/dashboard/summary', config)
  return data
}
