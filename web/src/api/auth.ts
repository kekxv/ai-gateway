import { api } from './index'
import type { User, LoginRequest, LoginResponse, RefreshResponse, ChangePasswordRequest, CreateUserRequest, UpdateUserRequest } from '@/types/user'
import type { TotpSetupResponse, TotpVerifyRequest, TotpDisableRequest } from '@/types/totp'

export const authApi = {
  // Login
  login: (data: LoginRequest) =>
    api.post<LoginResponse>('/auth/login', data),

  // Refresh token
  refreshToken: () =>
    api.post<RefreshResponse>('/auth/refresh'),

  // Get current user
  getCurrentUser: () =>
    api.get<User>('/users/me'),

  // Change password
  changePassword: (data: ChangePasswordRequest) =>
    api.post('/users/me/change-password', data),

  // TOTP setup
  setupTotp: () =>
    api.post<TotpSetupResponse>('/users/me/totp/setup'),

  // TOTP verify
  verifyTotp: (data: TotpVerifyRequest) =>
    api.post('/users/me/totp/verify', data),

  // TOTP disable
  disableTotp: (data: TotpDisableRequest) =>
    api.post('/users/me/totp/disable', data),

  // Get user stats
  getUserStats: () =>
    api.get('/users/me/stats')
}

interface UpdateBalanceRequest {
  amount: number
  action: string
}

export const userApi = {
  // List all users (returns full list, no pagination)
  list: () =>
    api.get<User[]>('/users'),

  // Get user by ID
  get: (id: number) =>
    api.get<User>(`/users/${id}`),

  // Create user
  create: (data: CreateUserRequest) =>
    api.post<User>('/users', data),

  // Update user
  update: (id: number, data: UpdateUserRequest) =>
    api.put<User>(`/users/${id}`, data),

  // Delete user
  delete: (id: number) =>
    api.delete(`/users/${id}`),

  // Update user balance
  updateBalance: (id: number, data: UpdateBalanceRequest) =>
    api.put(`/users/${id}/balance`, data),

  // Toggle user disabled status
  toggleDisabled: (id: number) =>
    api.post<User>(`/users/${id}/toggle-disabled`)
}