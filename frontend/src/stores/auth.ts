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
  let sessionRevision = 0

  const stopSessionInvalidatedListener = onSessionInvalidated(() => {
    sessionRevision += 1
    user.value = null
    ready.value = true
  })
  onScopeDispose(stopSessionInvalidatedListener)

  function clearSession(): void {
    sessionRevision += 1
    user.value = null
    clearSessionTokens()
  }

  function requireAdmin(currentUser: CurrentUser): void {
    if (currentUser.role !== 'admin') {
      clearSession()
      throw new ApiError(403, 'admin_required', '仅管理员可以访问管理控制台')
    }
  }

  function currentUserId(): number | null {
    return user.value?.id ?? null
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
    sessionRevision += 1
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

  async function refreshCurrentUser(signal?: AbortSignal): Promise<void> {
    if (user.value === null) {
      throw new ApiError(401, 'authentication_required', '登录状态已失效')
    }
    const startingUserId = user.value.id
    const startingRevision = ++sessionRevision
    const currentUser = await getCurrentUser(signal)
    if (
      signal?.aborted === true ||
      startingRevision !== sessionRevision ||
      currentUserId() !== startingUserId
    ) {
      throw new ApiError(401, 'session_changed', '登录状态已变更，请重试')
    }
    requireAdmin(currentUser)
    user.value = currentUser
  }

  function logout(): void {
    clearSession()
    ready.value = true
  }

  return { user, ready, authenticated, isAdmin, login, restore, refreshCurrentUser, logout }
})
