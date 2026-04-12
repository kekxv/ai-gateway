import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { skillApi } from '@/api/skill'
import type { Skill, SkillCatalogItem, CreateSkillRequest, UpdateSkillRequest } from '@/types/skill'
import { ElMessage } from 'element-plus'

export const useSkillsStore = defineStore('skills', () => {
  // Skills list
  const skills = ref<Skill[]>([])

  // Catalog for chat integration
  const catalog = ref<SkillCatalogItem[]>([])

  // Skills XML for chat prompt
  const skillsXML = ref<string>('')

  // Loading state
  const loading = ref(false)

  // Enabled skills (computed)
  const enabledSkills = computed(() => skills.value.filter(s => s.enabled))

  // Load skills from API
  async function loadSkills() {
    loading.value = true
    try {
      const response = await skillApi.list()
      skills.value = response.data?.data || []
    } catch (error) {
      console.error('Failed to load skills:', error)
    } finally {
      loading.value = false
    }
  }

  // Load catalog for chat integration
  async function loadCatalog() {
    try {
      const response = await skillApi.getCatalog()
      catalog.value = response.data?.data || []
      skillsXML.value = response.data?.xml || ''
    } catch (error) {
      console.error('Failed to load skills catalog:', error)
    }
  }

  // Create skill
  async function createSkill(data: CreateSkillRequest): Promise<Skill | null> {
    try {
      const response = await skillApi.create(data)
      const newSkill = response.data?.data
      if (newSkill) {
        skills.value.push(newSkill)
        ElMessage.success('Skill created successfully')
        return newSkill
      }
      return null
    } catch (error) {
      ElMessage.error('Failed to create skill')
      return null
    }
  }

  // Update skill
  async function updateSkill(id: number, data: UpdateSkillRequest): Promise<Skill | null> {
    try {
      const response = await skillApi.update(id, data)
      const updatedSkill = response.data?.data
      if (updatedSkill) {
        const index = skills.value.findIndex(s => s.id === id)
        if (index !== -1) {
          skills.value[index] = updatedSkill
        }
        ElMessage.success('Skill updated successfully')
        return updatedSkill
      }
      return null
    } catch (error) {
      ElMessage.error('Failed to update skill')
      return null
    }
  }

  // Delete skill
  async function deleteSkill(id: number): Promise<boolean> {
    try {
      await skillApi.delete(id)
      skills.value = skills.value.filter(s => s.id !== id)
      ElMessage.success('Skill deleted successfully')
      return true
    } catch (error) {
      ElMessage.error('Failed to delete skill')
      return false
    }
  }

  // Toggle skill enabled status
  async function toggleSkill(id: number): Promise<Skill | null> {
    try {
      const response = await skillApi.toggle(id)
      const updatedSkill = response.data?.data
      if (updatedSkill) {
        const index = skills.value.findIndex(s => s.id === id)
        if (index !== -1) {
          skills.value[index] = updatedSkill
        }
        return updatedSkill
      }
      return null
    } catch (error) {
      ElMessage.error('Failed to toggle skill')
      return null
    }
  }

  // Scan local skills
  async function scanLocalSkills(path?: string): Promise<Skill[]> {
    loading.value = true
    try {
      const response = await skillApi.scan(path)
      return response.data?.data || []
    } catch (error) {
      ElMessage.error('Failed to scan skills')
      return []
    } finally {
      loading.value = false
    }
  }

  // Import skill
  async function importSkill(path: string): Promise<Skill | null> {
    try {
      const response = await skillApi.import(path)
      const importedSkill = response.data?.data
      if (importedSkill) {
        skills.value.push(importedSkill)
        ElMessage.success('Skill imported successfully')
        return importedSkill
      }
      return null
    } catch (error) {
      ElMessage.error('Failed to import skill')
      return null
    }
  }

  // Get skills for model injection (returns XML for system prompt)
  function getSkillsForModel(): string {
    return skillsXML.value
  }

  // Get skill by name (for activation)
  function getSkillByName(name: string): Skill | undefined {
    return skills.value.find(s => s.name === name && s.enabled)
  }

  // Initialize on store creation
  loadSkills()
  loadCatalog()

  return {
    skills,
    catalog,
    skillsXML,
    loading,
    enabledSkills,
    loadSkills,
    loadCatalog,
    createSkill,
    updateSkill,
    deleteSkill,
    toggleSkill,
    scanLocalSkills,
    importSkill,
    getSkillsForModel,
    getSkillByName
  }
})