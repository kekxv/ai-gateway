import { apiClient } from './client'
import type { CatalogImportResult } from './types'

export async function exportCatalog(includeSecrets: boolean): Promise<Blob> {
  const { data } = await apiClient.get<Blob>('/admin/configuration/export', {
    params: { include_secrets: includeSecrets },
    responseType: 'blob',
  })
  return data
}

export async function importCatalog(bundleText: string): Promise<CatalogImportResult> {
  const { data } = await apiClient.post<CatalogImportResult>(
    '/admin/configuration/import',
    bundleText,
    { headers: { 'Content-Type': 'application/json' } },
  )
  return data
}
