import axios, {
  AxiosHeaders,
  type AxiosError,
  type InternalAxiosRequestConfig,
} from 'axios'

import type { AccessToken, ApiErrorBody, ApiValidationError } from './types'

export const ACCESS_TOKEN_KEY = 'gateway.access_token'
export const REFRESH_TOKEN_KEY = 'gateway.refresh_token'

interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
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
const sessionInvalidatedListeners = new Set<SessionInvalidatedListener>()

function advanceSessionGeneration(): void {
  sessionGeneration += 1
  refreshState = null
}

export function clearSessionTokens(): void {
  advanceSessionGeneration()
  sessionStorage.removeItem(ACCESS_TOKEN_KEY)
  sessionStorage.removeItem(REFRESH_TOKEN_KEY)
  for (const listener of sessionInvalidatedListeners) listener()
}

export function replaceSessionTokens(accessToken: string, refreshToken: string): void {
  advanceSessionGeneration()
  sessionStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  sessionStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
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
  admin_required: '仅管理员可以访问管理控制台',
  authentication_required: '请先登录管理控制台',
  current_totp_required: '请输入当前双重验证验证码',
  invalid_credentials: '邮箱或密码错误',
  invalid_token: '登录状态已失效',
  invalid_totp: '双重验证验证码无效',
  user_has_history: '用户已有请求或账本历史，请改为停用用户以保留审计记录',
  provider_has_history: '供应商已有请求历史，不能直接删除',
  session_changed: '登录状态已变更，请重试',
  totp_required: '请输入双重验证验证码',
}

const validationFieldLabels: Readonly<Record<string, string>> = {
  code: '验证码',
  current_totp_code: '当前验证码',
  email: '邮箱',
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

function safeApiMessage(code: string, status: number): string {
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
      safeApiMessage(body.detail.code, status),
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
    sessionStorage.getItem(REFRESH_TOKEN_KEY) === refreshToken
  )
}

function sessionChangedError(): ApiError {
  return new ApiError(401, 'session_changed', safeApiMessage('session_changed', 401))
}

async function refreshAccessToken(): Promise<RefreshedSession> {
  const refreshToken = sessionStorage.getItem(REFRESH_TOKEN_KEY)
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
    promise: rawClient
      .post<AccessToken>('/auth/refresh', { refresh_token: refreshToken })
      .then(({ data }) => {
        if (!sessionMatches(generation, refreshToken)) throw sessionChangedError()
        sessionStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
        return { accessToken: data.access_token, generation }
      })
      .catch((error: unknown) => {
        if (!sessionMatches(generation, refreshToken)) throw sessionChangedError()
        clearSessionTokens()
        throw normalizeApiError(error)
      }),
  }
  state.promise = state.promise.finally(() => {
    if (refreshState === state) refreshState = null
  })
  refreshState = state
  return state.promise
}

apiClient.interceptors.request.use((config: RetriableRequestConfig) => {
  config._sessionGeneration = sessionGeneration
  const accessToken = sessionStorage.getItem(ACCESS_TOKEN_KEY)
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
      sessionStorage.getItem(REFRESH_TOKEN_KEY) !== null

    if (!canRefresh) throw normalizeApiError(error)

    config._retried = true
    const refreshedSession = await refreshAccessToken()
    if (
      refreshedSession.generation !== sessionGeneration ||
      config._sessionGeneration !== refreshedSession.generation
    ) {
      throw sessionChangedError()
    }
    config.headers = AxiosHeaders.from(config.headers)
    config.headers.set('Authorization', `Bearer ${refreshedSession.accessToken}`)
    return apiClient.request(config)
  },
)
