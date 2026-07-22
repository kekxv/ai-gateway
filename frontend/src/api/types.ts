export type Protocol = 'openai' | 'claude' | 'gemini'
export type UserRole = 'admin' | 'user'
export type RequestStatus = 'started' | 'completed' | 'failed' | 'client_disconnected'
export type RouteRuntimeState = 'closed' | 'open' | 'half_open'
export type RouteSource = 'manual' | 'discovered'
export type ApiKeyScope = 'all' | 'providers' | 'models' | 'providers_and_models'
export type RoutingStrategy = 'weighted_random'
export type LedgerKind = 'reservation' | 'reservation_release' | 'usage' | 'adjustment'
export type UsageSource = 'provider' | 'estimated'

export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject
export type JsonObject = { [key: string]: JsonValue }

export interface LoginRequest {
  email: string
  password: string
  totp_code?: string | null
}

export interface RefreshRequest {
  refresh_token: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
}

export interface AccessToken {
  access_token: string
  token_type: 'bearer'
}

export interface CurrentUser {
  id: number
  email: string
  role: UserRole
  is_active: boolean
  totp_enabled: boolean
  created_at: string
  updated_at: string
}

export interface TotpSetupRequest {
  current_totp_code?: string | null
}

export interface TotpSetupResponse {
  otpauth_uri: string
}

export interface TotpConfirmRequest {
  code: string
}

export interface TotpConfirmResponse {
  totp_enabled: boolean
}

export interface ApiErrorDetail {
  code: string
  message: string
  request_id?: string
}

export interface ApiValidationError {
  loc: Array<string | number>
  msg: string
  type: string
}

export interface ApiErrorBody {
  detail: ApiErrorDetail | ApiValidationError[]
}

export interface ResourceCount {
  total: number
  enabled: number
}

export interface RouteCount extends ResourceCount {
  unavailable: number
}

export interface DailyUsagePoint {
  date: string
  requests: number
  failures: number
  cost: string
}

export interface DashboardSummary {
  users_total: number
  active_api_keys: number
  providers: ResourceCount
  models: ResourceCount
  routes: RouteCount
  requests_24h: number
  failed_requests_24h: number
  prompt_tokens_24h: number
  completion_tokens_24h: number
  cost_24h: string
  average_latency_ms_24h: number | null
  daily_usage: DailyUsagePoint[]
}

export interface UserCreate {
  email: string
  password: string
  role?: UserRole
  initial_balance?: string
}

export interface UserUpdate {
  email?: string | null
  password?: string | null
  role?: UserRole | null
  is_active?: boolean | null
}

export interface UserResponse {
  id: number
  email: string
  role: UserRole
  is_active: boolean
  balance: string
  created_at: string
  updated_at: string
}

export interface ProviderProtocolInput {
  id?: number | null
  protocol: Protocol
  base_url: string
  websocket_url?: string | null
  extra_headers?: JsonObject | null
  enabled?: boolean
}

export interface ProviderCreate {
  name: string
  credential: JsonObject
  enabled?: boolean
  auto_load_models?: boolean
  model_sync_interval_seconds?: number | null
  protocols?: ProviderProtocolInput[]
}

export interface ProviderUpdate {
  name?: string | null
  credential?: JsonObject | null
  enabled?: boolean | null
  auto_load_models?: boolean | null
  model_sync_interval_seconds?: number | null
  protocols?: ProviderProtocolInput[] | null
}

export interface ProviderProtocolResponse {
  id: number
  protocol: Protocol
  base_url: string
  websocket_url: string | null
  has_extra_headers: boolean
  enabled: boolean
}

export interface ProviderResponse {
  id: number
  name: string
  has_credential: boolean
  enabled: boolean
  auto_load_models: boolean
  model_sync_interval_seconds: number
  last_model_sync_at: string | null
  protocols: ProviderProtocolResponse[]
}

export interface ModelSyncResult {
  provider_id: number
  discovered_models: number
  created_models: number
  created_routes: number
  updated_routes: number
  disabled_routes: number
}

export interface ModelAliasInput {
  alias: string
  enabled?: boolean
}

export type AliasInput = string | ModelAliasInput

export interface ModelCreate {
  canonical_name: string
  display_name: string
  input_price_per_million?: string
  output_price_per_million?: string
  enabled?: boolean
  aliases?: AliasInput[]
  routing_strategy?: RoutingStrategy
}

export interface ModelUpdate {
  canonical_name?: string | null
  display_name?: string | null
  input_price_per_million?: string | null
  output_price_per_million?: string | null
  enabled?: boolean | null
  aliases?: AliasInput[] | null
  routing_strategy?: RoutingStrategy | null
}

export interface ModelAliasResponse {
  id: number
  alias: string
  enabled: boolean
}

export interface ModelResponse {
  id: number
  canonical_name: string
  display_name: string
  input_price_per_million: string
  output_price_per_million: string
  enabled: boolean
  aliases: ModelAliasResponse[]
  routing_strategy: RoutingStrategy
  created_at: string
  updated_at: string
}

export interface ModelRouteCreate {
  model_id: number
  provider_id: number
  provider_protocol_id: number
  upstream_model: string
  weight?: number
  enabled?: boolean
}

export interface ModelRouteUpdate {
  model_id?: number | null
  provider_id?: number | null
  provider_protocol_id?: number | null
  upstream_model?: string | null
  weight?: number | null
  enabled?: boolean | null
}

export interface ModelRouteResponse {
  id: number
  model_id: number
  provider_id: number
  provider_protocol_id: number
  upstream_model: string
  weight: number
  enabled: boolean
  source: RouteSource
  runtime_state: RouteRuntimeState
  consecutive_failures: number
  disabled_until: string | null
  last_error_code: string | null
  last_error_at: string | null
}

export interface ApiKeyCreate {
  user_id: number
  name: string
  scope?: ApiKeyScope
  is_active?: boolean
  expires_at?: string | null
  provider_ids?: number[]
  model_ids?: number[]
}

export interface ApiKeyUpdate {
  name?: string | null
  scope?: ApiKeyScope | null
  is_active?: boolean | null
  expires_at?: string | null
  provider_ids?: number[] | null
  model_ids?: number[] | null
}

export interface ApiKeyResponse {
  id: number
  user_id: number
  name: string
  key_prefix: string
  scope: ApiKeyScope
  is_active: boolean
  expires_at: string | null
  last_used_at: string | null
  created_at: string
  provider_ids: number[]
  model_ids: number[]
}

export interface ApiKeyCreatedResponse extends ApiKeyResponse {
  key: string
}

export interface BalanceAdjustmentCreate {
  amount: string
  reason: string
  idempotency_key: string
}

export interface BalanceResponse {
  balance: string
  total_spent: string
}

export interface BalanceAdjustmentResponse extends BalanceResponse {
  ledger_entry_id: number
  amount: string
}

export interface LedgerEntryResponse {
  id: number
  request_id: string | null
  idempotency_key: string
  kind: LedgerKind
  amount: string
  balance_after: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface RequestLogSummary {
  id: string
  user_id: number
  api_key_id: number | null
  model_id: number | null
  provider_id: number | null
  model_route_id: number | null
  inbound_protocol: Protocol
  outbound_protocol: Protocol | null
  transport: string
  stream: boolean
  status: RequestStatus
  http_status: number | null
  prompt_tokens: number
  completion_tokens: number
  usage_source: UsageSource | null
  cost: string
  latency_ms: number | null
  first_token_ms: number | null
  error_code: string | null
  created_at: string
  completed_at: string | null
}

export interface RequestLogListResponse {
  items: RequestLogSummary[]
  next_cursor: string | null
}

export interface RequestLogDetail extends RequestLogSummary {
  request_detail: Record<string, unknown> | null
  response_detail: Record<string, unknown> | null
}
