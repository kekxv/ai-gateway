// Provider types
export interface ProviderType {
  type: string
  baseURL: string
  createdAt?: string
}

export interface Provider {
  id: number
  name: string
  baseURL: string
  base_url?: string
  apiKey?: string
  api_key?: string
  type: string
  types?: string
  typesList?: string[]
  providerTypes?: ProviderType[]
  autoLoadModels: boolean
  auto_load_models?: boolean
  disabled?: boolean
  config?: string
  createdAt: string
  created_at?: string
}

export interface CreateProviderRequest {
  name: string
  baseURL?: string
  base_url?: string
  apiKey?: string
  api_key?: string
  type?: string
  types?: string
  typesList?: string[]
  providerTypes?: ProviderType[]
  autoLoadModels?: boolean
  auto_load_models?: boolean
  disabled?: boolean
  config?: string
}

export interface UpdateProviderRequest {
  name?: string
  baseURL?: string
  base_url?: string
  apiKey?: string
  api_key?: string
  type?: string
  types?: string
  typesList?: string[]
  providerTypes?: ProviderType[]
  autoLoadModels?: boolean
  auto_load_models?: boolean
  disabled?: boolean
  config?: string
}