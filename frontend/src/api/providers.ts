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

export async function createProvider(
  payload: ProviderCreate,
  signal?: AbortSignal,
): Promise<ProviderResponse> {
  const config = signal === undefined ? undefined : { signal }
  const { data } = await apiClient.post<ProviderResponse>('/admin/providers', payload, config)
  return data
}

export async function updateProvider(
  providerId: number,
  payload: ProviderUpdate,
  signal?: AbortSignal,
): Promise<ProviderResponse> {
  const config = signal === undefined ? undefined : { signal }
  const { data } = await apiClient.patch<ProviderResponse>(
    `/admin/providers/${String(providerId)}`,
    payload,
    config,
  )
  return data
}

export async function deleteProvider(providerId: number, signal?: AbortSignal): Promise<void> {
  const config = signal === undefined ? undefined : { signal }
  await apiClient.delete(`/admin/providers/${String(providerId)}`, config)
}

export async function syncProviderModels(
  providerId: number,
  signal?: AbortSignal,
): Promise<ModelSyncResult> {
  const config = signal === undefined ? undefined : { signal }
  const { data } = await apiClient.post<ModelSyncResult>(
    `/admin/providers/${String(providerId)}/sync-models`,
    undefined,
    config,
  )
  return data
}
