import { apiClient, normalizeApiError, rawClient } from './client'
import type {
  CurrentUser,
  LoginRequest,
  PasswordChangeRequest,
  RegisterRequest,
  TokenPair,
  TotpConfirmRequest,
  TotpConfirmResponse,
  TotpDisableRequest,
  TotpSetupRequest,
  TotpSetupResponse,
} from './types'

export async function login(credentials: LoginRequest, signal?: AbortSignal): Promise<TokenPair> {
  try {
    const { data } = await rawClient.post<TokenPair>(
      '/auth/login',
      credentials,
      signalConfig(signal),
    )
    return data
  } catch (error: unknown) {
    throw normalizeApiError(error)
  }
}

export async function register(
  credentials: RegisterRequest,
  signal?: AbortSignal,
): Promise<TokenPair> {
  try {
    const { data } = await rawClient.post<TokenPair>(
      '/auth/register',
      credentials,
      signalConfig(signal),
    )
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

export async function changePassword(
  payload: PasswordChangeRequest,
  signal?: AbortSignal,
): Promise<void> {
  await apiClient.post('/auth/password', payload, signalConfig(signal))
}

export async function disableTotp(
  payload: TotpDisableRequest,
  signal?: AbortSignal,
): Promise<TotpConfirmResponse> {
  const { data } = await apiClient.post<TotpConfirmResponse>(
    '/auth/totp/disable',
    payload,
    signalConfig(signal),
  )
  return data
}
