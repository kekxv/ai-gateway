import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import type { User, LoginRequest } from '@/types/user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<User | null>(
    localStorage.getItem('user') ? JSON.parse(localStorage.getItem('user')!) : null
  )
  const loading = ref(false)

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'ADMIN')

  const login = async (credentials: LoginRequest) => {
    loading.value = true
    try {
      const { data } = await authApi.login(credentials)
      token.value = data.token
      localStorage.setItem('token', data.token)

      // Fetch user info
      const { data: userData } = await authApi.getCurrentUser()
      user.value = userData
      localStorage.setItem('user', JSON.stringify(userData))

      return { success: true }
    } catch (error: any) {
      const errorMessage = error.response?.data?.error || '登录失败'
      return { success: false, error: errorMessage }
    } finally {
      loading.value = false
    }
  }

  const logout = () => {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  const fetchCurrentUser = async () => {
    if (!token.value) return
    try {
      const { data } = await authApi.getCurrentUser()
      user.value = data
      localStorage.setItem('user', JSON.stringify(data))
    } catch {
      clearAuth()
    }
  }

  const clearAuth = () => {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    isAdmin,
    login,
    logout,
    fetchCurrentUser,
    clearAuth
  }
})