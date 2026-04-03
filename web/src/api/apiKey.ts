import { api } from './index'
import type { GatewayAPIKey, CreateAPIKeyRequest, UpdateAPIKeyRequest } from '@/types/apiKey'

interface APIKeyListResponse {
  keys: GatewayAPIKey[]
  total: number
}

interface APIKeyCreateResponse {
  id: number
  key: string
  name: string
}

export const apiKeyApi = {
  // List all API keys
  list: (params?: { page?: number; page_size?: number }) =>
    api.get<APIKeyListResponse>('/keys', { params }),

  // Create API key
  create: (data: CreateAPIKeyRequest) =>
    api.post<APIKeyCreateResponse>('/keys', data),

  // Update API key
  update: (id: number, data: UpdateAPIKeyRequest) =>
    api.put<GatewayAPIKey>(`/keys/${id}`, data),

  // Delete API key
  delete: (id: number) =>
    api.delete(`/keys/${id}`)
}