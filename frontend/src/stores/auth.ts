import { computed, onScopeDispose, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  getCurrentUser,
  login as loginRequest,
  register as registerRequest,
} from '@/api/auth'
import {
  ACCESS_TOKEN_KEY,
  ApiError,
  clearSessionTokens,
  onSessionInvalidated,
  replaceSessionTokens,
  REFRESH_TOKEN_KEY,
} from '@/api/client'
import type { CurrentUser, LoginRequest, RegisterRequest, TokenPair } from '@/api/types'

interface AuthOperation {
  revision: number
  controller: AbortController
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const ready = ref(false)
  const authenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.role === 'admin')
  let sessionRevision = 0
  let activeAuthOperation: AuthOperation | undefined
  let operationInvalidatedBySessionFailure: AuthOperation | undefined

  function invalidateAuthOperation(): void {
    sessionRevision += 1
    activeAuthOperation?.controller.abort()
    activeAuthOperation = undefined
  }

  const stopSessionInvalidatedListener = onSessionInvalidated(() => {
    operationInvalidatedBySessionFailure = activeAuthOperation
    invalidateAuthOperation()
    user.value = null
    ready.value = true
  })
  onScopeDispose(stopSessionInvalidatedListener)

  function clearSession(): void {
    invalidateAuthOperation()
    user.value = null
    clearSessionTokens()
  }

  function beginAuthOperation(): AuthOperation {
    invalidateAuthOperation()
    operationInvalidatedBySessionFailure = undefined
    const operation = {
      revision: sessionRevision,
      controller: new AbortController(),
    }
    activeAuthOperation = operation
    return operation
  }

  function isCurrentAuthOperation(operation: AuthOperation): boolean {
    return (
      activeAuthOperation === operation &&
      operation.revision === sessionRevision &&
      !operation.controller.signal.aborted
    )
  }

  function sessionChangedError(): ApiError {
    return new ApiError(401, 'session_changed', '登录状态已变更，请重试')
  }

  function isOwnAuthenticationFailure(operation: AuthOperation, error: unknown): boolean {
    return (
      operationInvalidatedBySessionFailure === operation &&
      error instanceof ApiError &&
      (error.code === 'authentication_required' || error.code === 'invalid_token')
    )
  }

  function requireCurrentAuthOperation(operation: AuthOperation): void {
    if (!isCurrentAuthOperation(operation)) throw sessionChangedError()
  }

  function finishAuthOperation(operation: AuthOperation): void {
    requireCurrentAuthOperation(operation)
    ready.value = true
    activeAuthOperation = undefined
  }

  function currentUserId(): number | null {
    return user.value?.id ?? null
  }

  async function authenticate(
    request: (signal: AbortSignal) => Promise<TokenPair>,
  ): Promise<void> {
    clearSession()
    const operation = beginAuthOperation()
    try {
      const tokens = await request(operation.controller.signal)
      requireCurrentAuthOperation(operation)
      replaceSessionTokens(tokens.access_token, tokens.refresh_token)

      const currentUser = await getCurrentUser(operation.controller.signal)
      requireCurrentAuthOperation(operation)
      user.value = currentUser
    } catch (error: unknown) {
      requireCurrentAuthOperation(operation)
      clearSession()
      throw error
    } finally {
      if (isCurrentAuthOperation(operation)) finishAuthOperation(operation)
    }
  }

  async function login(credentials: LoginRequest): Promise<void> {
    await authenticate((signal) => loginRequest(credentials, signal))
  }

  async function register(credentials: RegisterRequest): Promise<void> {
    await authenticate((signal) => registerRequest(credentials, signal))
  }

  async function restore(): Promise<void> {
    const operation = beginAuthOperation()
    ready.value = false
    user.value = null
    const hasAccessToken = sessionStorage.getItem(ACCESS_TOKEN_KEY) !== null
    const hasRefreshToken = sessionStorage.getItem(REFRESH_TOKEN_KEY) !== null
    if (!hasAccessToken && !hasRefreshToken) {
      finishAuthOperation(operation)
      return
    }

    try {
      const currentUser = await getCurrentUser(operation.controller.signal)
      requireCurrentAuthOperation(operation)
      user.value = currentUser
    } catch (error: unknown) {
      if (isOwnAuthenticationFailure(operation, error)) return
      requireCurrentAuthOperation(operation)
      clearSession()
    } finally {
      if (isCurrentAuthOperation(operation)) finishAuthOperation(operation)
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
    user.value = currentUser
  }

  function logout(): void {
    clearSession()
    ready.value = true
  }

  return {
    user,
    ready,
    authenticated,
    isAdmin,
    login,
    register,
    restore,
    refreshCurrentUser,
    logout,
  }
})
