import { apiClient } from './client'
import type {
  Protocol,
  RequestLogDetail,
  RequestLogListResponse,
  RequestStatus,
  UserRequestLogDetail,
  UserRequestLogListResponse,
} from './types'

export interface RequestLogQuery {
  requestId?: string
  userId?: number
  apiKeyId?: number
  modelId?: number
  providerId?: number
  status?: RequestStatus
  protocol?: Protocol
  createdFrom?: string
  createdTo?: string
  cursor?: string
  pageSize?: number
}

type RequestLogParams = Partial<{
  request_id: string
  user_id: number
  api_key_id: number
  model_id: number
  provider_id: number
  status: RequestStatus
  protocol: Protocol
  created_from: string
  created_to: string
  cursor: string
  page_size: number
}>

function nonEmpty(value: string | undefined): string | undefined {
  const normalized = value?.trim()
  return normalized === '' ? undefined : normalized
}

function isoTimestamp(value: string | undefined): string | undefined {
  const normalized = nonEmpty(value)
  return normalized === undefined ? undefined : new Date(normalized).toISOString()
}

function adminQueryParams(query: RequestLogQuery): RequestLogParams {
  const params: RequestLogParams = {}
  const requestId = nonEmpty(query.requestId)
  const cursor = nonEmpty(query.cursor)
  const createdFrom = isoTimestamp(query.createdFrom)
  const createdTo = isoTimestamp(query.createdTo)

  if (requestId !== undefined) params.request_id = requestId
  if (query.userId !== undefined) params.user_id = query.userId
  if (query.apiKeyId !== undefined) params.api_key_id = query.apiKeyId
  if (query.modelId !== undefined) params.model_id = query.modelId
  if (query.providerId !== undefined) params.provider_id = query.providerId
  if (query.status !== undefined) params.status = query.status
  if (query.protocol !== undefined) params.protocol = query.protocol
  if (createdFrom !== undefined) params.created_from = createdFrom
  if (createdTo !== undefined) params.created_to = createdTo
  if (cursor !== undefined) params.cursor = cursor
  if (query.pageSize !== undefined) params.page_size = query.pageSize
  return params
}

function userQueryParams(query: RequestLogQuery): RequestLogParams {
  const params: RequestLogParams = {}
  const requestId = nonEmpty(query.requestId)
  const cursor = nonEmpty(query.cursor)
  const createdFrom = isoTimestamp(query.createdFrom)
  const createdTo = isoTimestamp(query.createdTo)

  if (requestId !== undefined) params.request_id = requestId
  if (query.apiKeyId !== undefined) params.api_key_id = query.apiKeyId
  if (query.modelId !== undefined) params.model_id = query.modelId
  if (query.status !== undefined) params.status = query.status
  if (query.protocol !== undefined) params.protocol = query.protocol
  if (createdFrom !== undefined) params.created_from = createdFrom
  if (createdTo !== undefined) params.created_to = createdTo
  if (cursor !== undefined) params.cursor = cursor
  if (query.pageSize !== undefined) params.page_size = query.pageSize
  return params
}

function signalConfig(signal?: AbortSignal): { signal: AbortSignal } | undefined {
  return signal === undefined ? undefined : { signal }
}

export async function listRequestLogs(
  query: RequestLogQuery = {},
  signal?: AbortSignal,
): Promise<RequestLogListResponse> {
  const { data } = await apiClient.get<RequestLogListResponse>('/admin/request-logs', {
    ...signalConfig(signal),
    params: adminQueryParams(query),
  })
  return data
}

export async function listUserRequestLogs(
  query: RequestLogQuery = {},
  signal?: AbortSignal,
): Promise<UserRequestLogListResponse> {
  const { data } = await apiClient.get<UserRequestLogListResponse>('/user/request-logs', {
    ...signalConfig(signal),
    params: userQueryParams(query),
  })
  return data
}

export async function getRequestLog(
  requestId: string,
  signal?: AbortSignal,
): Promise<RequestLogDetail> {
  const { data } = await apiClient.get<RequestLogDetail>(
    `/admin/request-logs/${encodeURIComponent(requestId)}`,
    signalConfig(signal),
  )
  return data
}

export async function getUserRequestLog(
  requestId: string,
  signal?: AbortSignal,
): Promise<UserRequestLogDetail> {
  const { data } = await apiClient.get<UserRequestLogDetail>(
    `/user/request-logs/${encodeURIComponent(requestId)}`,
    signalConfig(signal),
  )
  return data
}
