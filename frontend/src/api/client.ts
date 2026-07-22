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
}

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

export function clearSessionTokens(): void {
  sessionStorage.removeItem(ACCESS_TOKEN_KEY)
  sessionStorage.removeItem(REFRESH_TOKEN_KEY)
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

function validationMessage(errors: ApiValidationError[]): string {
  if (errors.length === 0) return '请求参数无效'
  return errors.map((error) => `${error.loc.join('.')}: ${error.msg}`).join('; ')
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
    return new ApiError(status, body.detail.code, body.detail.message, body.detail.request_id)
  }

  if (status === 401) return new ApiError(status, 'authentication_required', '登录状态已失效')
  if (status === 403) return new ApiError(status, 'forbidden', '没有权限执行此操作')
  if (status === 0) return new ApiError(status, 'network_error', '网络请求失败')
  return new ApiError(status, 'request_failed', `请求失败（HTTP ${String(status)}）`)
}

let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refreshToken = sessionStorage.getItem(REFRESH_TOKEN_KEY)
  if (refreshToken === null) {
    throw new ApiError(401, 'authentication_required', '登录状态已失效')
  }

  refreshPromise ??= rawClient
    .post<AccessToken>('/auth/refresh', { refresh_token: refreshToken })
    .then(({ data }) => {
      sessionStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
      return data.access_token
    })
    .finally(() => {
      refreshPromise = null
    })
  return refreshPromise
}

apiClient.interceptors.request.use((config) => {
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
    const canRefresh =
      error.response?.status === 401 &&
      config !== undefined &&
      config._retried !== true &&
      sessionStorage.getItem(REFRESH_TOKEN_KEY) !== null

    if (!canRefresh) throw normalizeApiError(error)

    config._retried = true
    try {
      const accessToken = await refreshAccessToken()
      config.headers = AxiosHeaders.from(config.headers)
      config.headers.set('Authorization', `Bearer ${accessToken}`)
      return await apiClient.request(config)
    } catch (refreshError: unknown) {
      clearSessionTokens()
      throw normalizeApiError(refreshError)
    }
  },
)
