import { computed, onScopeDispose, ref } from 'vue'
import { defineStore } from 'pinia'

import { getCurrentUser, login as loginRequest } from '@/api/auth'
import {
  ACCESS_TOKEN_KEY,
  ApiError,
  clearSessionTokens,
  onSessionInvalidated,
  replaceSessionTokens,
  REFRESH_TOKEN_KEY,
} from '@/api/client'
import type { CurrentUser, LoginRequest } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const ready = ref(false)
  const authenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.role === 'admin')

  const stopSessionInvalidatedListener = onSessionInvalidated(() => {
    user.value = null
    ready.value = true
  })
  onScopeDispose(stopSessionInvalidatedListener)

  function clearSession(): void {
    user.value = null
    clearSessionTokens()
  }

  function requireAdmin(currentUser: CurrentUser): void {
    if (currentUser.role !== 'admin') {
      clearSession()
      throw new ApiError(403, 'admin_required', '仅管理员可以访问管理控制台')
    }
  }

  async function login(credentials: LoginRequest): Promise<void> {
    clearSession()
    try {
      const tokens = await loginRequest(credentials)
      replaceSessionTokens(tokens.access_token, tokens.refresh_token)

      const currentUser = await getCurrentUser()
      requireAdmin(currentUser)
      user.value = currentUser
    } catch (error: unknown) {
      clearSession()
      throw error
    } finally {
      ready.value = true
    }
  }

  async function restore(): Promise<void> {
    ready.value = false
    user.value = null
    const hasAccessToken = sessionStorage.getItem(ACCESS_TOKEN_KEY) !== null
    const hasRefreshToken = sessionStorage.getItem(REFRESH_TOKEN_KEY) !== null
    if (!hasAccessToken && !hasRefreshToken) {
      ready.value = true
      return
    }

    try {
      const currentUser = await getCurrentUser()
      requireAdmin(currentUser)
      user.value = currentUser
    } catch {
      clearSession()
    } finally {
      ready.value = true
    }
  }

  function logout(): void {
    clearSession()
    ready.value = true
  }

  return { user, ready, authenticated, isAdmin, login, restore, logout }
})
