import { apiClient } from './client'
import type {
  AdminBillingStatisticsResponse,
  UserBillingStatisticsResponse,
} from './types'

export interface UserBillingStatisticsQuery {
  startAt: string
  endAt: string
  modelIds: number[]
  apiKeyIds: number[]
}

export interface AdminBillingStatisticsQuery extends UserBillingStatisticsQuery {
  providerIds: number[]
}

function paramsFor(query: UserBillingStatisticsQuery, providerIds: number[] = []): URLSearchParams {
  const params = new URLSearchParams({ start_at: query.startAt, end_at: query.endAt })
  for (const providerId of providerIds) params.append('provider_ids', String(providerId))
  for (const modelId of query.modelIds) params.append('model_ids', String(modelId))
  for (const apiKeyId of query.apiKeyIds) params.append('api_key_ids', String(apiKeyId))
  return params
}

export async function getAdminBillingStatistics(
  query: AdminBillingStatisticsQuery,
  signal?: AbortSignal,
): Promise<AdminBillingStatisticsResponse> {
  const params = paramsFor(query, query.providerIds)
  const config = signal === undefined ? { params } : { params, signal }
  const { data } = await apiClient.get<AdminBillingStatisticsResponse>('/admin/billing-statistics', config)
  return data
}

export async function getUserBillingStatistics(
  query: UserBillingStatisticsQuery,
  signal?: AbortSignal,
): Promise<UserBillingStatisticsResponse> {
  const params = paramsFor(query)
  const config = signal === undefined ? { params } : { params, signal }
  const { data } = await apiClient.get<UserBillingStatisticsResponse>('/user/billing-statistics', config)
  return data
}
