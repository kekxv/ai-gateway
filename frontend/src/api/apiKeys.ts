import { apiClient } from './client'
import type {
  ApiKeyCreate,
  ApiKeyCreatedResponse,
  ApiKeyResponse,
  ApiKeyUpdate,
  SelfApiKeyCreate,
  SelfApiKeyUpdate,
} from './types'

function signalConfig(signal?: AbortSignal): { signal: AbortSignal } | undefined {
  return signal === undefined ? undefined : { signal }
}

export async function listApiKeys(
  userId?: number,
  signal?: AbortSignal,
): Promise<ApiKeyResponse[]> {
  const config = {
    ...signalConfig(signal),
    params: userId === undefined ? undefined : { user_id: userId },
  }
  const { data } = await apiClient.get<ApiKeyResponse[]>('/admin/api-keys', config)
  return data
}

export async function createApiKey(
  payload: ApiKeyCreate,
  signal?: AbortSignal,
): Promise<ApiKeyCreatedResponse> {
  const { data } = await apiClient.post<ApiKeyCreatedResponse>(
    '/admin/api-keys',
    payload,
    signalConfig(signal),
  )
  return data
}

export async function updateApiKey(
  apiKeyId: number,
  payload: ApiKeyUpdate,
  signal?: AbortSignal,
): Promise<ApiKeyResponse> {
  const { data } = await apiClient.patch<ApiKeyResponse>(
    `/admin/api-keys/${String(apiKeyId)}`,
    payload,
    signalConfig(signal),
  )
  return data
}

export async function deleteApiKey(apiKeyId: number, signal?: AbortSignal): Promise<void> {
  await apiClient.delete(`/admin/api-keys/${String(apiKeyId)}`, signalConfig(signal))
}

export async function rotateApiKey(
  apiKeyId: number,
  signal?: AbortSignal,
): Promise<ApiKeyCreatedResponse> {
  const { data } = await apiClient.post<ApiKeyCreatedResponse>(
    `/admin/api-keys/${String(apiKeyId)}/rotate`,
    undefined,
    signalConfig(signal),
  )
  return data
}

export async function listOwnApiKeys(signal?: AbortSignal): Promise<ApiKeyResponse[]> {
  const { data } = await apiClient.get<ApiKeyResponse[]>('/user/api-keys', signalConfig(signal))
  return data
}

export async function createOwnApiKey(
  payload: SelfApiKeyCreate,
  signal?: AbortSignal,
): Promise<ApiKeyCreatedResponse> {
  const { data } = await apiClient.post<ApiKeyCreatedResponse>(
    '/user/api-keys',
    payload,
    signalConfig(signal),
  )
  return data
}

export async function updateOwnApiKey(
  apiKeyId: number,
  payload: SelfApiKeyUpdate,
  signal?: AbortSignal,
): Promise<ApiKeyResponse> {
  const { data } = await apiClient.patch<ApiKeyResponse>(
    `/user/api-keys/${String(apiKeyId)}`,
    payload,
    signalConfig(signal),
  )
  return data
}

export async function deleteOwnApiKey(apiKeyId: number, signal?: AbortSignal): Promise<void> {
  await apiClient.delete(`/user/api-keys/${String(apiKeyId)}`, signalConfig(signal))
}

export async function rotateOwnApiKey(
  apiKeyId: number,
  signal?: AbortSignal,
): Promise<ApiKeyCreatedResponse> {
  const { data } = await apiClient.post<ApiKeyCreatedResponse>(
    `/user/api-keys/${String(apiKeyId)}/rotate`,
    undefined,
    signalConfig(signal),
  )
  return data
}
