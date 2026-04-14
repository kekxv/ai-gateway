// Channel types
export interface Channel {
  id: number
  name: string
  enabled: boolean
  shared: boolean
  supportsAllModels?: boolean
  userId?: number
  // Associated providers (many-to-many)
  providers?: { id: number; name: string }[]
  // Allowed models (many-to-many)
  allowedModels?: { id: number; name: string }[]
  // Legacy support
  models?: (number | { id: number; name: string })[]
  providerId?: number
  provider_ids?: number[]
  createdAt: string
  updatedAt: string
  created_at?: string
  updated_at?: string
}

export interface CreateChannelRequest {
  name: string
  enabled?: boolean
  shared?: boolean
  supportsAllModels?: boolean
}

export interface UpdateChannelRequest {
  name?: string
  enabled?: boolean
  shared?: boolean
  supportsAllModels?: boolean
}

export interface BindProvidersRequest {
  provider_ids: number[]
}

export interface BindModelsRequest {
  model_ids: number[]
}