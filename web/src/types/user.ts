// User types
export interface User {
  id: number
  email: string
  role: 'ADMIN' | 'USER'
  disabled: boolean
  validUntil: string | null
  balance: number
  totpEnabled: boolean
  createdAt: string
}

export interface LoginRequest {
  email: string
  password: string
  totp?: string
  totpToken?: string
}

export interface LoginResponse {
  message: string
  token: string
  role: string
  user?: User
}

export interface RefreshResponse {
  token: string
}

export interface ChangePasswordRequest {
  currentPassword: string
  newPassword: string
  current_password?: string
  new_password?: string
}

export interface CreateUserRequest {
  email: string
  password: string
  role: 'ADMIN' | 'USER'
  balance?: number
  disabled?: boolean
  validUntil?: string
  valid_until?: string
}

export interface UpdateUserRequest {
  email?: string
  role?: 'ADMIN' | 'USER'
  balance?: number
  disabled?: boolean
  validUntil?: string | null
  valid_until?: string | null
}