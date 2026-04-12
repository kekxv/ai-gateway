import axios, { type AxiosInstance, type AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

// 不需要处理401跳转的接口列表（认证相关接口）
const AUTH_ENDPOINTS = ['/auth/login', '/auth/register', '/auth/refresh']

const createApiInstance = (): AxiosInstance => {
  const instance = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json'
    }
  })

  // Request interceptor - add JWT token
  instance.interceptors.request.use(
    (config) => {
      const token = localStorage.getItem('token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    },
    (error) => Promise.reject(error)
  )

  // Response interceptor - handle errors
  instance.interceptors.response.use(
    (response) => response,
    (error: AxiosError<{ error?: string }>) => {
      const requestUrl = error.config?.url || ''
      const isAuthEndpoint = AUTH_ENDPOINTS.some(endpoint => requestUrl.includes(endpoint))

      if (error.response?.status === 401) {
        // 认证相关接口的401不跳转（登录失败、注册失败等）
        if (!isAuthEndpoint) {
          // 清除认证信息
          localStorage.removeItem('token')
          localStorage.removeItem('user')

          // 跳转到登录页（使用 hash 导航，不刷新页面）
          if (window.location.hash !== '#/login') {
            window.location.hash = '#/login'
          }
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