import { apiClient } from './client'
import type {
  BalanceAdjustmentCreate,
  BalanceAdjustmentResponse,
  LedgerEntryResponse,
  UserCreate,
  UserResponse,
  UserUpdate,
} from './types'

function signalConfig(signal?: AbortSignal): { signal: AbortSignal } | undefined {
  return signal === undefined ? undefined : { signal }
}

export async function listUsers(signal?: AbortSignal): Promise<UserResponse[]> {
  const { data } = await apiClient.get<UserResponse[]>('/admin/users', signalConfig(signal))
  return data
}

export async function createUser(
  payload: UserCreate,
  signal?: AbortSignal,
): Promise<UserResponse> {
  const { data } = await apiClient.post<UserResponse>(
    '/admin/users',
    payload,
    signalConfig(signal),
  )
  return data
}

export async function updateUser(
  userId: number,
  payload: UserUpdate,
  signal?: AbortSignal,
): Promise<UserResponse> {
  const { data } = await apiClient.patch<UserResponse>(
    `/admin/users/${String(userId)}`,
    payload,
    signalConfig(signal),
  )
  return data
}

export async function deleteUser(userId: number, signal?: AbortSignal): Promise<void> {
  await apiClient.delete(`/admin/users/${String(userId)}`, signalConfig(signal))
}

export async function adjustBalance(
  userId: number,
  payload: BalanceAdjustmentCreate,
  signal?: AbortSignal,
): Promise<BalanceAdjustmentResponse> {
  const { data } = await apiClient.post<BalanceAdjustmentResponse>(
    `/admin/users/${String(userId)}/balance-adjustments`,
    payload,
    signalConfig(signal),
  )
  return data
}

export async function listLedger(
  userId: number,
  signal?: AbortSignal,
): Promise<LedgerEntryResponse[]> {
  const { data } = await apiClient.get<LedgerEntryResponse[]>(
    `/admin/users/${String(userId)}/ledger`,
    signalConfig(signal),
  )
  return data
}
