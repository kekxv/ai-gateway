import { apiClient } from './client'
import type {
  ModelSyncResult,
  ProviderCreate,
  ProviderResponse,
  ProviderUpdate,
} from './types'

export async function listProviders(signal?: AbortSignal): Promise<ProviderResponse[]> {
  const config = signal === undefined ? undefined : { signal }
  const { data } = await apiClient.get<ProviderResponse[]>('/admin/providers', config)
  return data
}

export async function createProvider(payload: ProviderCreate): Promise<ProviderResponse> {
  const { data } = await apiClient.post<ProviderResponse>('/admin/providers', payload)
  return data
}

export async function updateProvider(
  providerId: number,
  payload: ProviderUpdate,
): Promise<ProviderResponse> {
  const { data } = await apiClient.patch<ProviderResponse>(
    `/admin/providers/${String(providerId)}`,
    payload,
  )
  return data
}

export async function deleteProvider(providerId: number): Promise<void> {
  await apiClient.delete(`/admin/providers/${String(providerId)}`)
}

export async function syncProviderModels(providerId: number): Promise<ModelSyncResult> {
  const { data } = await apiClient.post<ModelSyncResult>(
    `/admin/providers/${String(providerId)}/sync-models`,
  )
  return data
}
