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

function signalConfig(signal?: AbortSignal): { signal: AbortSignal } | undefined {
  return signal === undefined ? undefined : { signal }
}

export async function getCurrentUser(signal?: AbortSignal): Promise<CurrentUser> {
  const { data } = await apiClient.get<CurrentUser>('/auth/me', signalConfig(signal))
  return data
}

export async function setupTotp(
  payload: TotpSetupRequest = {},
  signal?: AbortSignal,
): Promise<TotpSetupResponse> {
  const { data } = await apiClient.post<TotpSetupResponse>(
    '/auth/totp/setup',
    payload,
    signalConfig(signal),
  )
  return data
}

export async function confirmTotp(
  payload: TotpConfirmRequest,
  signal?: AbortSignal,
): Promise<TotpConfirmResponse> {
  const { data } = await apiClient.post<TotpConfirmResponse>(
    '/auth/totp/confirm',
    payload,
    signalConfig(signal),
  )
  return data
}
