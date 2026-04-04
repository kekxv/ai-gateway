import { api } from './index'
import type { Provider, CreateProviderRequest, UpdateProviderRequest } from '@/types/provider'

export const providerApi = {
  // List all providers (returns full list, no pagination)
  list: () =>
    api.get<Provider[]>('/providers'),

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
    api.post(`/providers/${id}/sync-models`),

  // Add models to provider (creates models and routes)
  addModels: (id: number, data: { models: { name: string; description?: string }[] }) =>
    api.post(`/providers/${id}/add-models`, data)
}