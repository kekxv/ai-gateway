// Skill types following agentskills.io standard

export interface Skill {
  id: number
  user_id: number
  name: string
  display_name?: string
  description: string
  location?: string
  instructions?: string
  license?: string
  compatibility?: string
  metadata?: string
  allowed_tools?: string
  source: string
  enabled: boolean
  created_at: string
  updated_at: string
  resources?: SkillResource[]
}

export interface SkillResource {
  id: number
  skill_id: number
  type: 'script' | 'reference' | 'asset'
  name: string
  path?: string
  content?: string
  created_at: string
}

export interface SkillCatalogItem {
  name: string
  description: string
  location: string
  source: string
  enabled: boolean
}

export interface CreateSkillRequest {
  name: string
  display_name?: string
  description: string
  location?: string
  instructions?: string
  license?: string
  compatibility?: string
  metadata?: string
  allowed_tools?: string
  source?: string
  enabled?: boolean
}

export interface UpdateSkillRequest {
  display_name?: string
  description?: string
  instructions?: string
  license?: string
  compatibility?: string
  metadata?: string
  allowed_tools?: string
  enabled?: boolean
}