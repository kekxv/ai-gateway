import { api } from './index'
import type { Skill, SkillCatalogItem, CreateSkillRequest, UpdateSkillRequest } from '@/types/skill'

export const skillApi = {
  // List all skills for current user
  list: () =>
    api.get<{ data: Skill[] }>('/skills'),

  // Get skill by ID
  get: (id: number) =>
    api.get<{ data: Skill }>(`/skills/${id}`),

  // Create skill
  create: (data: CreateSkillRequest) =>
    api.post<{ data: Skill }>('/skills', data),

  // Update skill
  update: (id: number, data: UpdateSkillRequest) =>
    api.put<{ data: Skill }>(`/skills/${id}`, data),

  // Delete skill
  delete: (id: number) =>
    api.delete(`/skills/${id}`),

  // Toggle skill enabled status
  toggle: (id: number) =>
    api.post<{ data: Skill }>(`/skills/${id}/toggle`),

  // Get skills catalog for chat integration
  getCatalog: () =>
    api.get<{ data: SkillCatalogItem[]; xml: string }>('/skills/catalog'),

  // Scan local directories for skills
  scan: (path?: string) =>
    api.get<{ data: Skill[] }>('/skills/scan', { params: { path } }),

  // Import a local skill into database
  import: (path: string) =>
    api.post<{ data: Skill }>('/skills/import', { path })
}