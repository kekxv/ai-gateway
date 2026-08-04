import { apiClient } from './client'
import type { DashboardDays, DashboardSummary, UserDashboardSummary } from './types'

export async function getDashboardSummary(
  signal?: AbortSignal,
  days?: DashboardDays,
): Promise<DashboardSummary> {
  const params = days !== undefined ? { days } : undefined
  const config = signal === undefined ? undefined : { signal, params }
  const { data } = await apiClient.get<DashboardSummary>('/admin/dashboard/summary', config)
  return data
}

export async function getUserDashboardSummary(
  signal?: AbortSignal,
  days?: DashboardDays,
): Promise<UserDashboardSummary> {
  const params = days !== undefined ? { days } : undefined
  const config = signal === undefined ? undefined : { signal, params }
  const { data } = await apiClient.get<UserDashboardSummary>('/me/dashboard/summary', config)
  return data
}
