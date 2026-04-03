import { api } from './index'
import type { Model, ModelRoute, CreateModelRequest, UpdateModelRequest, UpdateModelPricesRequest } from '@/types/model'

interface ModelListResponse {
  models: Model[]
  total: number
}

interface RouteListResponse {
  routes: ModelRoute[]
}

export const modelApi = {
  // List all models
  list: (params?: { page?: number; page_size?: number; name?: string }) =>
    api.get<ModelListResponse>('/models', { params }),

  // Get model by ID
  get: (id: number) =>
    api.get<Model>(`/models/${id}`),

  // Create model
  create: (data: CreateModelRequest) =>
    api.post<Model>('/models', data),

  // Update model
  update: (id: number, data: UpdateModelRequest) =>
    api.put<Model>(`/models/${id}`, data),

  // Delete model
  delete: (id: number) =>
    api.delete(`/models/${id}`),

  // Update model prices
  updatePrices: (id: number, data: UpdateModelPricesRequest) =>
    api.put(`/models/${id}/prices`, data),

  // Get model routes
  getRoutes: (id: number) =>
    api.get<RouteListResponse>(`/models/${id}/routes`),

  // Update model routes
  updateRoutes: (id: number, routes: Partial<ModelRoute>[]) =>
    api.put(`/models/${id}/routes`, { routes }),

  // Create model route
  createRoute: (data: { modelId: number; providerId: number; weight?: number }) =>
    api.post<ModelRoute>('/model-routes', data),

  // Update model route weight
  updateRouteWeight: (routeId: number, weight: number) =>
    api.put(`/model-routes/${routeId}/weight`, { weight })
}