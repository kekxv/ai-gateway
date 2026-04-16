import axios, { type AxiosInstance, type AxiosError } from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

// 不需要处理401跳转的接口列表（认证相关接口）
const AUTH_ENDPOINTS = ['/auth/login', '/auth/register', '/auth/refresh']

// Token刷新相关状态
let isRefreshing = false
let refreshSubscribers: Array<(token: string) => void> = []
let isRedirecting = false

// JWT过期时间检查阈值：在过期前15分钟刷新token
const REFRESH_THRESHOLD_MINUTES = 15

/**
 * 解析JWT token获取payload
 */
function parseJwt(token: string): { exp?: number; [key: string]: unknown } | null {
  try {
    const base64Url = token.split('.')[1]
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    )
    return JSON.parse(jsonPayload)
  } catch {
    return null
  }
}

/**
 * 检查token是否需要刷新
 * 如果token将在REFRESH_THRESHOLD_MINUTES分钟内过期，返回true
 */
function shouldRefreshToken(token: string): boolean {
  const payload = parseJwt(token)
  if (!payload || !payload.exp) return false

  const expiresAt = payload.exp * 1000 // 转换为毫秒
  const now = Date.now()
  const threshold = REFRESH_THRESHOLD_MINUTES * 60 * 1000 // 转换为毫秒

  return expiresAt - now < threshold
}

/**
 * 检查token是否已过期
 */
function isTokenExpired(token: string): boolean {
  const payload = parseJwt(token)
  if (!payload || !payload.exp) return true

  return payload.exp * 1000 < Date.now()
}

/**
 * 订阅token刷新
 */
function subscribeTokenRefresh(callback: (token: string) => void) {
  refreshSubscribers.push(callback)
}

/**
 * 通知所有订阅者token已刷新
 */
function onTokenRefreshed(token: string) {
  refreshSubscribers.forEach(callback => callback(token))
  refreshSubscribers = []
}

/**
 * 刷新token
 */
async function refreshToken(api: AxiosInstance): Promise<string | null> {
  const token = localStorage.getItem('token')
  if (!token) return null

  try {
    const response = await api.post<{ token: string }>('/auth/refresh')
    const newToken = response.data.token
    localStorage.setItem('token', newToken)

    // 更新auth store
    const authStore = useAuthStore()
    authStore.setToken(newToken)

    return newToken
  } catch (error) {
    console.error('Token refresh failed:', error)
    return null
  }
}

const createApiInstance = (): AxiosInstance => {
  const instance = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json'
    }
  })

  // Request interceptor - add JWT token and check if refresh needed
  instance.interceptors.request.use(
    async (config) => {
      const token = localStorage.getItem('token')
      if (!token) return config

      // 如果是refresh接口本身，直接添加token
      if (config.url?.includes('/auth/refresh')) {
        config.headers.Authorization = `Bearer ${token}`
        return config
      }

      // 检查token是否已过期
      if (isTokenExpired(token)) {
        // Token已过期，清除认证信息并跳转登录页
        const authStore = useAuthStore()
        authStore.clearAuth()
        if (!isRedirecting) {
          isRedirecting = true
          ElMessage.error('登录已过期，请重新登录')
          window.location.href = '/#/login'
        }
        return Promise.reject(new Error('Token expired'))
      }

      // 检查是否需要刷新token
      if (shouldRefreshToken(token) && !isRefreshing) {
        isRefreshing = true
        try {
          const newToken = await refreshToken(instance)
          if (newToken) {
            onTokenRefreshed(newToken)
            config.headers.Authorization = `Bearer ${newToken}`
          } else {
            config.headers.Authorization = `Bearer ${token}`
          }
        } finally {
          isRefreshing = false
        }
      } else if (isRefreshing) {
        // 正在刷新token，等待刷新完成
        return new Promise((resolve) => {
          subscribeTokenRefresh((newToken: string) => {
            config.headers.Authorization = `Bearer ${newToken}`
            resolve(config)
          })
        })
      } else {
        config.headers.Authorization = `Bearer ${token}`
      }

      return config
    },
    (error) => Promise.reject(error)
  )

  // Response interceptor - handle errors
  instance.interceptors.response.use(
    (response) => response,
    async (error: AxiosError<{ error?: string }>) => {
      const requestUrl = error.config?.url || ''
      const isAuthEndpoint = AUTH_ENDPOINTS.some(endpoint => requestUrl.includes(endpoint))

      if (error.response?.status === 401) {
        // 认证相关接口的401不跳转（登录失败、注册失败等）
        if (!isAuthEndpoint && !isRedirecting) {
          isRedirecting = true

          // Clear auth store state (this also clears localStorage)
          const authStore = useAuthStore()
          authStore.clearAuth()

          ElMessage.error('登录已过期，请重新登录')

          // 跳转到登录页 - 使用 window.location 强制刷新
          window.location.href = '/#/login'
          window.location.reload()
        }
      } else if (error.response?.status === 403) {
        ElMessage.error('权限不足')
      } else if (!isAuthEndpoint) {
        // 非认证接口才显示全局错误提示
        const message = error.response?.data?.error || error.message || '请求失败'
        ElMessage.error(message)
      }
      return Promise.reject(error)
    }
  )

  return instance
}

export const api = createApiInstance()

/**
 * 页面离开时刷新token
 * 使用 fetch keepalive 确保请求在页面卸载后仍能完成
 */
function refreshOnUnload() {
  const token = localStorage.getItem('token')
  if (!token) return

  // 只有token需要刷新时才发送请求
  if (!shouldRefreshToken(token)) return

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api'

  // 使用 fetch keepalive，请求会在页面卸载后继续进行
  fetch(`${apiBaseUrl}/auth/refresh`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    keepalive: true
  })
    .then(response => response.json())
    .then((data: { token?: string }) => {
      if (data.token) {
        localStorage.setItem('token', data.token)
      }
    })
    .catch(error => {
      console.error('Unload refresh failed:', error)
    })
}

// 注册页面离开事件
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', refreshOnUnload)
}