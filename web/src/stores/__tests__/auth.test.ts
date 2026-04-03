import { vi, describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import type { AxiosResponse } from 'axios'

const createMockResponse = <T>(data: T): AxiosResponse<T> => ({
  data,
  status: 200,
  statusText: 'OK',
  headers: {},
  config: { headers: {} } as any
} as any) // Cast to any to bypass strict type checking for tests

// Mock auth API
vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn(),
    getCurrentUser: vi.fn()
  }
}))

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn()
}
vi.stubGlobal('localStorage', localStorageMock)

// Mock router
vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({
    push: vi.fn()
  })),
  useRoute: vi.fn(() => ({
    path: '/dashboard'
  })),
  createRouter: vi.fn(() => ({
    push: vi.fn(),
    replace: vi.fn(),
    go: vi.fn(),
    beforeEach: vi.fn(),
    currentRoute: { value: { path: '/dashboard' } }
  })),
  createWebHashHistory: vi.fn()
}))

// Mock the router import
vi.mock('@/router', () => ({
  router: {
    push: vi.fn()
  }
}))

describe('Auth Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorageMock.getItem.mockReturnValue(null)
  })

  describe('initial state', () => {
    it('should have null token initially', () => {
      const store = useAuthStore()
      expect(store.token).toBeNull()
    })

    it('should have null user initially', () => {
      const store = useAuthStore()
      expect(store.user).toBeNull()
    })

    it('should not be authenticated initially', () => {
      const store = useAuthStore()
      expect(store.isAuthenticated).toBe(false)
    })

    it('should not be admin initially', () => {
      const store = useAuthStore()
      expect(store.isAdmin).toBe(false)
    })
  })

  describe('login action', () => {
    it('should login successfully', async () => {
      const store = useAuthStore()
      vi.mocked(authApi.login).mockResolvedValue(createMockResponse({ token: 'test-token' }) as any)
      vi.mocked(authApi.getCurrentUser).mockResolvedValue(createMockResponse({ id: 1, email: 'test@example.com', role: 'USER' }) as any)

      const result = await store.login({ email: 'test@example.com', password: 'password' })

      expect(authApi.login).toHaveBeenCalledWith({
        email: 'test@example.com',
        password: 'password'
      })
      expect(authApi.getCurrentUser).toHaveBeenCalled()
      expect(store.token).toBe('test-token')
      expect(store.user).toEqual({ id: 1, email: 'test@example.com', role: 'USER' })
      expect(result).toEqual({ success: true })
    })

    it('should login with TOTP', async () => {
      const store = useAuthStore()
      vi.mocked(authApi.login).mockResolvedValue(createMockResponse({ token: 'test-token' }) as any)
      vi.mocked(authApi.getCurrentUser).mockResolvedValue(createMockResponse({ id: 1, email: 'test@example.com', role: 'USER' }) as any)

      await store.login({ email: 'test@example.com', password: 'password', totp: '123456' })

      expect(authApi.login).toHaveBeenCalledWith({
        email: 'test@example.com',
        password: 'password',
        totp: '123456'
      })
    })

    it('should return error on login failure', async () => {
      const store = useAuthStore()
      vi.mocked(authApi.login).mockRejectedValue({
        response: { data: { error: 'Invalid credentials' } }
      })

      const result = await store.login({ email: 'test@example.com', password: 'wrong' })

      expect(result).toEqual({ success: false, error: 'Invalid credentials' })
    })
  })

  describe('logout action', () => {
    it('should clear token and user on logout', () => {
      const store = useAuthStore()
      store.token = 'test-token'
      store.user = { id: 1, email: 'test@example.com', role: 'USER' } as any

      store.logout()

      expect(store.token).toBeNull()
      expect(store.user).toBeNull()
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('token')
    })
  })

  describe('fetchCurrentUser action', () => {
    it('should fetch current user', async () => {
      const store = useAuthStore()
      store.token = 'test-token'
      vi.mocked(authApi.getCurrentUser).mockResolvedValue(createMockResponse({ id: 1, email: 'test@example.com', role: 'USER' }) as any)

      await store.fetchCurrentUser()

      expect(authApi.getCurrentUser).toHaveBeenCalled()
      expect(store.user).toEqual({ id: 1, email: 'test@example.com', role: 'USER' })
    })

    it('should not fetch if no token', async () => {
      const store = useAuthStore()
      store.token = null

      await store.fetchCurrentUser()

      expect(authApi.getCurrentUser).not.toHaveBeenCalled()
    })
  })

  describe('computed properties', () => {
    it('should be authenticated when token exists', () => {
      const store = useAuthStore()
      store.token = 'test-token'

      expect(store.isAuthenticated).toBe(true)
    })

    it('should be admin when user role is ADMIN', () => {
      const store = useAuthStore()
      store.user = { id: 1, email: 'admin@example.com', role: 'ADMIN' } as any

      expect(store.isAdmin).toBe(true)
    })

    it('should not be admin when user role is USER', () => {
      const store = useAuthStore()
      store.user = { id: 1, email: 'user@example.com', role: 'USER' } as any

      expect(store.isAdmin).toBe(false)
    })
  })
})