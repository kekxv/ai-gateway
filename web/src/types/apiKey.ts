// API Key types
export interface GatewayAPIKey {
  id: number
  key: string
  name: string
  enabled: boolean
  bindToAllChannels: boolean
  bind_to_all?: boolean
  logDetails: boolean
  log_details?: boolean
  userId?: number
  lastUsed?: string
  last_used?: string
  channels?: (number | { id: number; name: string })[]
  models?: (number | { id: number; name: string })[]
  createdAt: string
  created_at?: string
}

export interface CreateAPIKeyRequest {
  name: string
  enabled?: boolean
  bind_to_all?: boolean
  log_details?: boolean
  channels?: number[]
  models?: number[]
}

export interface UpdateAPIKeyRequest {
  name?: string
  enabled?: boolean
  bind_to_all?: boolean
  log_details?: boolean
  channels?: number[]
  models?: number[]
}