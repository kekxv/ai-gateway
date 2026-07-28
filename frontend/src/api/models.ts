import { apiClient } from './client'
import type {
  ModelCreate,
  ModelResponse,
  ModelRouteCreate,
  ModelRouteResponse,
  ModelRouteUpdate,
  ModelUpdate,
} from './types'

export interface ModelRouteFilters {
  model_id?: number
  provider_id?: number
}

function signalConfig(signal?: AbortSignal): { signal: AbortSignal } | undefined {
  return signal === undefined ? undefined : { signal }
}

export async function listModels(signal?: AbortSignal): Promise<ModelResponse[]> {
  const { data } = await apiClient.get<ModelResponse[]>('/admin/models', signalConfig(signal))
  return data
}

export async function listAvailableModels(signal?: AbortSignal): Promise<ModelResponse[]> {
  const { data } = await apiClient.get<ModelResponse[]>('/user/models', signalConfig(signal))
  return data
}

export async function createModel(
  payload: ModelCreate,
  signal?: AbortSignal,
): Promise<ModelResponse> {
  const { data } = await apiClient.post<ModelResponse>(
    '/admin/models',
    payload,
    signalConfig(signal),
  )
  return data
}

export async function updateModel(
  modelId: number,
  payload: ModelUpdate,
  signal?: AbortSignal,
): Promise<ModelResponse> {
  const { data } = await apiClient.patch<ModelResponse>(
    `/admin/models/${String(modelId)}`,
    payload,
    signalConfig(signal),
  )
  return data
}

export async function deleteModel(modelId: number, signal?: AbortSignal): Promise<void> {
  await apiClient.delete(`/admin/models/${String(modelId)}`, signalConfig(signal))
}

export async function listModelRoutes(
  filters: ModelRouteFilters = {},
  signal?: AbortSignal,
): Promise<ModelRouteResponse[]> {
  const config = {
    ...signalConfig(signal),
    params: filters,
  }
  const { data } = await apiClient.get<ModelRouteResponse[]>('/admin/model-routes', config)
  return data
}

export async function createModelRoute(
  payload: ModelRouteCreate,
  signal?: AbortSignal,
): Promise<ModelRouteResponse> {
  const { data } = await apiClient.post<ModelRouteResponse>(
    '/admin/model-routes',
    payload,
    signalConfig(signal),
  )
  return data
}

export async function updateModelRoute(
  routeId: number,
  payload: ModelRouteUpdate,
  signal?: AbortSignal,
): Promise<ModelRouteResponse> {
  const { data } = await apiClient.patch<ModelRouteResponse>(
    `/admin/model-routes/${String(routeId)}`,
    payload,
    signalConfig(signal),
  )
  return data
}

export async function deleteModelRoute(routeId: number, signal?: AbortSignal): Promise<void> {
  await apiClient.delete(`/admin/model-routes/${String(routeId)}`, signalConfig(signal))
}
