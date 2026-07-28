import { apiClient } from './client'
import type { RegistrationSetting } from './types'

function signalConfig(signal?: AbortSignal): { signal: AbortSignal } | undefined {
  return signal === undefined ? undefined : { signal }
}

export async function getRegistrationSetting(
  signal?: AbortSignal,
): Promise<RegistrationSetting> {
  const { data } = await apiClient.get<RegistrationSetting>(
    '/admin/settings/registration',
    signalConfig(signal),
  )
  return data
}

export async function updateRegistrationSetting(
  enabled: boolean,
  signal?: AbortSignal,
): Promise<RegistrationSetting> {
  const { data } = await apiClient.patch<RegistrationSetting>(
    '/admin/settings/registration',
    { enabled },
    signalConfig(signal),
  )
  return data
}
