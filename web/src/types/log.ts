// Log types
export interface APIKeyInfo {
  id: number
  name: string
  user?: {
    id: number
    email: string
    role: string
  }
}

export interface ChannelInfo {
  id: number
  name: string
  user?: {
    id: number
    email: string
  }
}

export interface Log {
  id: number
  model?: string
  modelName?: string
  model_name?: string
  provider?: string
  providerName?: string
  provider_name?: string
  latency_ms?: number
  latency?: number
  promptTokens?: number
  prompt_tokens?: number
  completionTokens?: number
  completion_tokens?: number
  totalTokens?: number
  total_tokens?: number
  tokens?: number
  cost: number
  status: number | string
  errorMessage?: string
  error_message?: string
  apiKeyId?: number
  apiKey?: APIKeyInfo
  ownerChannelId?: number
  ownerChannel?: ChannelInfo
  ownerChannelUserId?: number
  requestHeaders?: string
  responseHeaders?: string
  createdAt: string
  created_at?: string
}

export interface LogDetailData {
  requestBody?: string
  responseBody?: string
}

export interface LogDetailResponse {
  log: Log
  detail: LogDetailData | null
}

export interface LogDetail extends Log {
  detail?: LogDetailData
}

export interface LogListResponse {
  logs: Log[]
  total: number
  page: number
  limit: number
}