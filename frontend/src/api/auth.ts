import { apiClient, normalizeApiError, rawClient } from './client'
import type {
  CurrentUser,
  LoginRequest,
  TokenPair,
  TotpConfirmRequest,
  TotpConfirmResponse,
  TotpSetupRequest,
  TotpSetupResponse,
} from './types'

export async function login(credentials: LoginRequest): Promise<TokenPair> {
  try {
    const { data } = await rawClient.post<TokenPair>('/auth/login', credentials)
    return data
  } catch (error: unknown) {
    throw normalizeApiError(error)
  }
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const { data } = await apiClient.get<CurrentUser>('/auth/me')
  return data
}

export async function setupTotp(payload?: TotpSetupRequest): Promise<TotpSetupResponse> {
  const { data } = await apiClient.post<TotpSetupResponse>('/auth/totp/setup', payload)
  return data
}

export async function confirmTotp(payload: TotpConfirmRequest): Promise<TotpConfirmResponse> {
  const { data } = await apiClient.post<TotpConfirmResponse>('/auth/totp/confirm', payload)
  return data
}
