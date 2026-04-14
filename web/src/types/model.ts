// Model types
export interface ModelRoute {
  id: number
  modelId: number
  model_id?: number
  channelId: number
  channel_id?: number
  channelName?: string
  channel_name?: string
  providerId: number
  provider_id?: number
  providerName?: string
  provider_name?: string
  modelName: string
  model_name?: string
  weight: number
  disabled: boolean
  disabledUntil: string | null
  provider?: {
    id: number
    name: string
  }
}

export interface Model {
  id: number
  name: string
  aliases?: string[]
  description?: string
  inputTokenPrice: number
  input_price?: number
  outputTokenPrice: number
  output_price?: number
  userId?: number
  createdAt: string
  updatedAt: string
  created_at?: string
  updated_at?: string
  modelRoutes?: ModelRoute[]
  routes?: ModelRoute[]
}

export interface CreateModelRequest {
  name: string
  aliases?: string[]
  description?: string
  input_price?: number
  output_price?: number
  channelIds?: number[]
  routes?: ModelRoute[]
}

export interface UpdateModelRequest {
  name?: string
  aliases?: string[]
  description?: string
  input_price?: number
  output_price?: number
}

export interface UpdateModelPricesRequest {
  inputTokenPrice: number
  outputTokenPrice: number
}