import axios, {
  AxiosHeaders,
  type AxiosError,
  type InternalAxiosRequestConfig,
} from 'axios'

import type { ApiErrorBody, ApiValidationError, TokenPair } from './types'

export const ACCESS_TOKEN_KEY = 'gateway.access_token'
export const REFRESH_TOKEN_KEY = 'gateway.refresh_token'

interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
  _syncRetried?: boolean
  _sessionGeneration?: number
}

interface RefreshedSession {
  accessToken: string
  generation: number
}

interface RefreshState {
  generation: number
  refreshToken: string
  promise: Promise<RefreshedSession>
}

type SessionInvalidatedListener = () => void

export class ApiError extends Error {
  public readonly requestId: string | undefined

  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    requestId?: string,
  ) {
    super(message)
    this.name = 'ApiError'
    this.requestId = requestId
  }
}

export const rawClient = axios.create()
export const apiClient = axios.create()

let sessionGeneration = 0
let refreshState: RefreshState | null = null
let lastAttemptedRefreshToken: string | null = null
const sessionInvalidatedListeners = new Set<SessionInvalidatedListener>()

// Proactive refresh timer state
let proactiveRefreshTimer: ReturnType<typeof setInterval> | null = null
const PROACTIVE_REFRESH_INTERVAL_MS = 10 * 60 * 1000 // 10 minutes

// Cross-tab sync via BroadcastChannel
let broadcastChannel: BroadcastChannel | null = null
try {
  broadcastChannel = new BroadcastChannel('gateway-auth')
  broadcastChannel.addEventListener('message', (event: MessageEvent) => {
    const data = event.data as { type?: string; access_token?: string; refresh_token?: string } | null
    if (data?.type === 'tokens-updated' && data.access_token && data.refresh_token) {
      const currentRefresh = localStorage.getItem(REFRESH_TOKEN_KEY)
      if (currentRefresh !== data.refresh_token) {
        advanceSessionGeneration()
        localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
        localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token)
      }
    }
  })
} catch {
  // BroadcastChannel not available in this environment
}

// Listen for storage events from other tabs
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event: StorageEvent) => {
    if (event.key === REFRESH_TOKEN_KEY && event.newValue !== null) {
      const currentRefresh = localStorage.getItem(REFRESH_TOKEN_KEY)
      if (currentRefresh !== event.newValue) {
        advanceSessionGeneration()
      }
    } else if (
      event.key === REFRESH_TOKEN_KEY &&
      event.newValue === null &&
      localStorage.getItem(ACCESS_TOKEN_KEY) === null
    ) {
      // Another tab cleared tokens
      for (const listener of sessionInvalidatedListeners) listener()
    }
  })
}

function advanceSessionGeneration(): void {
  sessionGeneration += 1
  refreshState = null
}

export function clearSessionTokens(): void {
  advanceSessionGeneration()
  lastAttemptedRefreshToken = null
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  if (broadcastChannel) {
    broadcastChannel.postMessage({ type: 'tokens-cleared' })
  }
  for (const listener of sessionInvalidatedListeners) listener()
}

export function replaceSessionTokens(accessToken: string, refreshToken: string): void {
  advanceSessionGeneration()
  lastAttemptedRefreshToken = null
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  broadcastTokens(accessToken, refreshToken)
}

/**
 * Update tokens within the same session (e.g. after refresh-token rotation).
 * Does NOT advance the session generation — stale-refresh detection still works.
 */
function rotateSessionTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  broadcastTokens(accessToken, refreshToken)
}

function broadcastTokens(accessToken: string, refreshToken: string): void {
  if (broadcastChannel) {
    broadcastChannel.postMessage({
      type: 'tokens-updated',
      access_token: accessToken,
      refresh_token: refreshToken,
    })
  }
}

/**
 * Check if another tab has already refreshed the tokens.
 * Returns true if the stored refresh token differs from the one we last tried
 * (meaning another tab updated it), so the caller can retry with the new tokens.
 */
function syncFromStorage(): boolean {
  const storedRefresh = localStorage.getItem(REFRESH_TOKEN_KEY)
  if (!storedRefresh) return false
  if (!localStorage.getItem(ACCESS_TOKEN_KEY)) return false
  // Only consider it a cross-tab sync if the stored token is DIFFERENT
  // from the one we just tried. If it's the same, no other tab refreshed.
  return storedRefresh !== lastAttemptedRefreshToken
}

export function onSessionInvalidated(listener: SessionInvalidatedListener): () => void {
  sessionInvalidatedListeners.add(listener)
  return () => {
    sessionInvalidatedListeners.delete(listener)
  }
}

function isValidationError(value: unknown): value is ApiValidationError {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return (
    Array.isArray(candidate.loc) &&
    candidate.loc.every((part) => typeof part === 'string' || typeof part === 'number') &&
    typeof candidate.msg === 'string' &&
    typeof candidate.type === 'string'
  )
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('detail' in value)) return false
  const detail = (value as Record<string, unknown>).detail
  if (Array.isArray(detail)) return detail.every(isValidationError)
  if (typeof detail !== 'object' || detail === null) return false
  const candidate = detail as Record<string, unknown>
  return (
    typeof candidate.code === 'string' &&
    typeof candidate.message === 'string' &&
    (candidate.request_id === undefined || typeof candidate.request_id === 'string')
  )
}

const apiErrorMessages: Readonly<Record<string, string>> = {
  account_not_found: '账户不存在',
  admin_required: '仅管理员可以访问管理控制台',
  ambiguous_credentials: '凭据配置不明确',
  ambiguous_model_name: '模型名称存在歧义',
  api_key_inactive: '接口密钥已停用',
  api_key_not_found: '接口密钥不存在',
  authentication_required: '请先登录管理控制台',
  credential_required: '请提供凭据',
  current_totp_required: '请输入当前双重验证验证码',
  duplicate_provider_protocol: '供应商协议配置重复',
  email_exists: '邮箱已被注册',
  invalid_api_key: '接口密钥无效',
  invalid_credentials: '邮箱或密码错误',
  invalid_cursor: '分页游标无效',
  invalid_provider_protocol: '供应商协议无效',
  invalid_retention_days: '保留天数无效',
  invalid_route_reference: '路由引用无效',
  invalid_scope_reference: '作用域引用无效',
  invalid_token: '登录状态已失效',
  invalid_token_type: '令牌类型无效',
  invalid_totp: '双重验证验证码无效',
  model_conflict: '模型配置冲突',
  model_discovery_failed: '模型发现失败',
  model_discovery_unavailable: '模型发现服务不可用',
  model_has_history: '模型已有请求历史，请改为停用模型以保留审计记录',
  model_name_conflict: '模型名称冲突',
  model_not_found: '模型不存在',
  model_route_conflict: '该模型和供应商的路由已存在',
  model_route_not_found: '模型路由不存在',
  provider_conflict: '供应商配置冲突',
  provider_has_history: '供应商已有请求历史，不能直接删除',
  provider_not_found: '供应商不存在',
  provider_protocol_in_use: '供应商协议正在使用中',
  provider_protocol_mismatch: '供应商协议不匹配',
  registration_disabled: '管理员已关闭公开注册',
  request_log_not_found: '请求日志不存在',
  self_delete_forbidden: '不能删除当前登录账户',
  self_disable_forbidden: '不能停用当前登录账户',
  session_changed: '登录状态已变更，请重试',
  totp_not_configured: '未配置双重验证',
  totp_not_enabled: '双重验证尚未启用',
  totp_required: '请输入双重验证验证码',
  user_disabled: '用户已停用',
  user_has_history: '用户已有请求或账本历史，请改为停用用户以保留审计记录',
  user_not_found: '用户不存在',
}

const validationFieldLabels: Readonly<Record<string, string>> = {
  admin_totp_code: '管理员验证码',
  code: '验证码',
  current_password: '当前密码',
  current_totp_code: '当前验证码',
  email: '邮箱',
  new_password: '新密码',
  password: '密码',
  refresh_token: '刷新令牌',
  totp_code: '验证码',
}

function validationMessage(errors: ApiValidationError[]): string {
  const labels = new Set<string>()
  for (const error of errors) {
    const field = error.loc[error.loc.length - 1]
    if (typeof field === 'string') labels.add(validationFieldLabels[field] ?? '请求')
  }
  return labels.size === 0 ? '请求参数无效' : `${[...labels].join('、')}参数无效`
}

function safeApiMessage(code: string, status: number, serverMessage?: string): string {
  if (code === 'model_discovery_failed' && serverMessage?.trim()) return serverMessage
  const knownMessage = apiErrorMessages[code]
  if (knownMessage !== undefined) return knownMessage
  if (status === 400) return '请求内容无效'
  if (status === 401) return '登录状态已失效'
  if (status === 403) return '没有权限执行此操作'
  if (status === 404) return '请求的资源不存在'
  if (status === 409) return '操作发生冲突，请刷新后重试'
  if (status === 422) return '请求参数无效'
  if (status === 429) return '请求过于频繁，请稍后重试'
  if (status >= 500) return '服务暂时不可用，请稍后重试'
  return '请求失败，请稍后重试'
}

export function normalizeApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  if (!axios.isAxiosError(error)) {
    return new ApiError(0, 'unexpected_error', '发生未知错误')
  }

  const status = error.response?.status ?? 0
  const body: unknown = error.response?.data
  if (isApiErrorBody(body)) {
    if (Array.isArray(body.detail)) {
      return new ApiError(status, 'validation_error', validationMessage(body.detail))
    }
    return new ApiError(
      status,
      body.detail.code,
      safeApiMessage(body.detail.code, status, body.detail.message),
      body.detail.request_id,
    )
  }

  if (status === 401) return new ApiError(status, 'authentication_required', '登录状态已失效')
  if (status === 403) return new ApiError(status, 'forbidden', '没有权限执行此操作')
  if (status === 0) return new ApiError(status, 'network_error', '网络请求失败')
  return new ApiError(status, 'request_failed', `请求失败（HTTP ${String(status)}）`)
}

function sessionMatches(generation: number, refreshToken: string): boolean {
  return (
    sessionGeneration === generation &&
    localStorage.getItem(REFRESH_TOKEN_KEY) === refreshToken
  )
}

function sessionChangedError(): ApiError {
  return new ApiError(401, 'session_changed', safeApiMessage('session_changed', 401))
}

async function refreshAccessToken(): Promise<RefreshedSession> {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
  if (refreshToken === null) {
    throw new ApiError(401, 'authentication_required', '登录状态已失效')
  }

  const generation = sessionGeneration
  if (
    refreshState !== null &&
    refreshState.generation === generation &&
    refreshState.refreshToken === refreshToken
  ) {
    return refreshState.promise
  }

  const state: RefreshState = {
    generation,
    refreshToken,
    promise: (async () => {
      lastAttemptedRefreshToken = refreshToken
      try {
        const { data } = await rawClient.post<TokenPair>('/auth/refresh', {
          refresh_token: refreshToken,
        })
        // Only update tokens when the refresh matches the current session.
        // If a new login happened while this refresh was in flight, the stored
        // refresh token (and generation) will have changed — leave them alone
        // so the fresh login tokens are not overwritten by stale refresh data.
        if (!sessionMatches(generation, refreshToken)) throw sessionChangedError()
        rotateSessionTokens(data.access_token, data.refresh_token)
        return { accessToken: data.access_token, generation }
      } catch (error: unknown) {
        if (!sessionMatches(generation, refreshToken)) throw sessionChangedError()
        clearSessionTokens()
        throw normalizeApiError(error)
      }
    })(),
  }
  state.promise = state.promise.finally(() => {
    if (refreshState === state) refreshState = null
  })
  refreshState = state
  return state.promise
}

apiClient.interceptors.request.use((config: RetriableRequestConfig) => {
  config._sessionGeneration = sessionGeneration
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (accessToken !== null) {
    config.headers.set('Authorization', `Bearer ${accessToken}`)
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableRequestConfig | undefined
    const belongsToCurrentSession = config?._sessionGeneration === sessionGeneration
    if (error.response?.status === 401 && !belongsToCurrentSession) {
      throw sessionChangedError()
    }

    const canRefresh =
      error.response?.status === 401 &&
      config !== undefined &&
      config._retried !== true &&
      belongsToCurrentSession &&
      localStorage.getItem(REFRESH_TOKEN_KEY) !== null

    if (canRefresh) {
      config._retried = true
      try {
        const refreshedSession = await refreshAccessToken()
        if (config._sessionGeneration !== refreshedSession.generation) {
          throw sessionChangedError()
        }
        config.headers = AxiosHeaders.from(config.headers)
        config.headers.set('Authorization', `Bearer ${refreshedSession.accessToken}`)
        return await apiClient.request(config)
      } catch (refreshError: unknown) {
        // Before giving up, check if another tab already refreshed the tokens.
        // If so, pick up the new tokens and retry the original request.
        if (
          config._syncRetried !== true &&
          refreshError instanceof ApiError &&
          (refreshError.code === 'invalid_token' ||
            refreshError.code === 'authentication_required' ||
            refreshError.code === 'session_changed')
        ) {
          if (syncFromStorage()) {
            config._syncRetried = true
            const freshAccess = localStorage.getItem(ACCESS_TOKEN_KEY)
            if (freshAccess) {
              config.headers = AxiosHeaders.from(config.headers)
              config.headers.set('Authorization', `Bearer ${freshAccess}`)
              return apiClient.request(config)
            }
          }
        }
        throw refreshError
      }
    }

    throw normalizeApiError(error)
  },
)

// Proactive refresh timer

function handleVisibilityChange(): void {
  if (typeof document === 'undefined') return
  if (document.visibilityState === 'visible' && proactiveRefreshTimer !== null) {
    // Refresh immediately on becoming visible, then restart the timer
    refreshAccessToken().catch(() => {
      // Silently ignore — the 401 interceptor will handle it
    })
  }
}

export function startProactiveRefresh(): void {
  if (proactiveRefreshTimer !== null) return // Already running
  proactiveRefreshTimer = setInterval(() => {
    const hasTokens =
      localStorage.getItem(ACCESS_TOKEN_KEY) !== null &&
      localStorage.getItem(REFRESH_TOKEN_KEY) !== null
    if (!hasTokens) {
      stopProactiveRefresh()
      return
    }
    refreshAccessToken().catch(() => {
      // Silently ignore — the 401 interceptor will handle it
    })
  }, PROACTIVE_REFRESH_INTERVAL_MS)

  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange)
  }
}

export function stopProactiveRefresh(): void {
  if (proactiveRefreshTimer !== null) {
    clearInterval(proactiveRefreshTimer)
    proactiveRefreshTimer = null
  }
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  }
}
