import { api } from './index'
import type { Provider, CreateProviderRequest, UpdateProviderRequest } from '@/types/provider'

interface ProviderListResponse {
  providers: Provider[]
  total: number
}

export const providerApi = {
  // List all providers
  list: (params?: { page?: number; page_size?: number }) =>
    api.get<ProviderListResponse>('/providers', { params }),

  // Get provider by ID
  get: (id: number) =>
    api.get<Provider>(`/providers/${id}`),

  // Create provider
  create: (data: CreateProviderRequest) =>
    api.post<Provider>('/providers', data),

  // Update provider
  update: (id: number, data: UpdateProviderRequest) =>
    api.put<Provider>(`/providers/${id}`, data),

  // Delete provider
  delete: (id: number) =>
    api.delete(`/providers/${id}`),

  // Load models from provider
  loadModels: (id: number) =>
    api.get(`/providers/${id}/load-models`),

  // Sync models from provider
  syncModels: (id: number) =>
    api.post(`/providers/${id}/sync-models`)
}