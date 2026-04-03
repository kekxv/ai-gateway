import axios, { type AxiosInstance, type AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

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
      const isLoginRequest = error.config?.url?.includes('/auth/login')

      if (error.response?.status === 401) {
        // 只在非登录页面清除 token 并跳转
        // 登录页面的 401 错误（密码错误等）应该由登录逻辑处理
        const currentPath = window.location.hash.replace('#', '')
        if (currentPath !== '/login') {
          localStorage.removeItem('token')
          localStorage.removeItem('user')
          window.location.hash = '#/login'
        }
      } else if (error.response?.status === 403) {
        ElMessage.error('权限不足')
      } else if (!isLoginRequest) {
        // 非登录请求才显示全局错误提示
        const message = error.response?.data?.error || error.message || '请求失败'
        ElMessage.error(message)
      }
      return Promise.reject(error)
    }
  )

  return instance
}

export const api = createApiInstance()