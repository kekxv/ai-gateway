<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('skill.title') }}</h2>
      <div class="flex gap-2">
        <el-button @click="showScanDialog = true">
          <el-icon><Search /></el-icon>
          {{ t('skill.scan') }}
        </el-button>
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          {{ t('common.create') }}
        </el-button>
      </div>
    </div>

    <!-- Skills List -->
    <div v-if="skillsStore.loading" class="text-center py-12">
      <el-icon class="is-loading" :size="40"><Loading /></el-icon>
    </div>
    <div v-else-if="skillsStore.skills.length === 0" class="text-center py-12">
      <div class="text-gray-500 mb-6">{{ t('common.noData') }}</div>
      <el-button type="primary" @click="addExampleSkill" :loading="addingExample">
        <el-icon><Plus /></el-icon>
        {{ t('skill.addExample') }}
      </el-button>
    </div>
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      <div
        v-for="skill in skillsStore.skills"
        :key="skill.id"
        class="bg-white rounded-lg shadow-sm border border-gray-100 p-4 hover:shadow-md transition-shadow"
      >
        <!-- Header: Name + Status -->
        <div class="flex items-center justify-between mb-3">
          <h3 class="font-semibold text-gray-800 truncate">{{ skill.display_name || skill.name }}</h3>
          <el-tag :type="skill.enabled ? 'success' : 'info'" size="small">
            {{ skill.enabled ? t('common.enabled') : t('common.disabled') }}
          </el-tag>
        </div>

        <!-- Source indicator -->
        <div class="flex items-center gap-2 mb-3">
          <el-tag size="small" effect="plain">{{ skill.source }}</el-tag>
          <span class="text-xs text-gray-400">{{ skill.name }}</span>
        </div>

        <!-- Description -->
        <p class="text-sm text-gray-600 mb-3 line-clamp-2">{{ skill.description }}</p>

        <!-- Resources indicator -->
        <div v-if="skill.resources && skill.resources.length > 0" class="flex items-center gap-1 mb-3">
          <el-tag size="small" type="info" effect="plain">
            {{ skill.resources.length }} {{ t('skill.resources') }}
          </el-tag>
        </div>

        <!-- Actions -->
        <div class="flex flex-wrap gap-2 pt-3 border-t border-gray-100">
          <el-button size="small" link type="info" @click="openDetailDialog(skill)">
            {{ t('skill.view') }}
          </el-button>
          <el-button size="small" link type="primary" @click="openEditDialog(skill)">
            {{ t('common.edit') }}
          </el-button>
          <el-button size="small" link :type="skill.enabled ? 'warning' : 'success'" @click="toggleEnabled(skill)">
            {{ skill.enabled ? t('common.disable') : t('common.enable') }}
          </el-button>
          <el-button size="small" link type="danger" @click="deleteSkill(skill)">
            {{ t('common.delete') }}
          </el-button>
        </div>
      </div>
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? t('skill.editTitle') : t('skill.createTitle')" :width="isMobile ? '90%' : '600px'">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" label-position="top">
        <el-form-item :label="t('skill.name')" prop="name">
          <el-input v-model="form.name" :disabled="isEdit" placeholder="e.g., code-review" />
          <div class="form-hint">{{ t('skill.nameHint') }}</div>
        </el-form-item>
        <el-form-item :label="t('skill.displayName')">
          <el-input v-model="form.display_name" placeholder="Friendly display name" />
        </el-form-item>
        <el-form-item :label="t('skill.description')" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="Skill description..." />
        </el-form-item>
        <el-form-item :label="t('skill.instructions')">
          <el-input v-model="form.instructions" type="textarea" :rows="6" placeholder="SKILL.md body content - detailed instructions..." />
        </el-form-item>
        <el-form-item :label="t('skill.license')">
          <el-select v-model="form.license" clearable class="w-full">
            <el-option label="MIT" value="MIT" />
            <el-option label="Apache 2.0" value="Apache-2.0" />
            <el-option label="GPL" value="GPL" />
            <el-option label="Proprietary" value="Proprietary" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('skill.allowedTools')">
          <el-input v-model="form.allowed_tools" placeholder="JSON array: [&quot;web_search&quot;, &quot;execute_javascript&quot;]" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- Scan Dialog -->
    <el-dialog v-model="showScanDialog" :title="t('skill.scanTitle')" :width="isMobile ? '90%' : '500px'">
      <div class="space-y-4">
        <el-form-item :label="t('skill.scanPath')">
          <el-input v-model="scanPath" placeholder="Project path to scan (default: current directory)" />
        </el-form-item>
        <el-button type="primary" @click="scanSkills" :loading="scanning">
          <el-icon><Search /></el-icon>
          {{ t('skill.scan') }}
        </el-button>

        <!-- Scanned results -->
        <div v-if="scannedSkills.length > 0" class="mt-4">
          <h4 class="text-sm font-medium mb-2">{{ t('skill.scanResult', { count: scannedSkills.length }) }}</h4>
          <div class="space-y-2">
            <div v-for="skill in scannedSkills" :key="skill.name" class="flex items-center justify-between p-2 bg-gray-50 rounded">
              <div>
                <span class="font-medium">{{ skill.name }}</span>
                <p class="text-xs text-gray-500">{{ skill.description }}</p>
              </div>
              <el-button size="small" type="primary" @click="importSkill(skill)">
                {{ t('skill.import') }}
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- Skill Detail Dialog -->
    <el-dialog v-model="detailDialogVisible" :title="detailSkill?.display_name || detailSkill?.name" :width="isMobile ? '90%' : '700px'">
      <div class="space-y-4">
        <!-- Basic Info -->
        <div class="bg-gray-50 rounded-lg p-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <span class="text-xs text-gray-500">{{ t('skill.name') }}</span>
              <p class="font-medium">{{ detailSkill?.name }}</p>
            </div>
            <div>
              <span class="text-xs text-gray-500">{{ t('skill.source') }}</span>
              <p class="font-medium">{{ detailSkill?.source }}</p>
            </div>
            <div class="col-span-2">
              <span class="text-xs text-gray-500">{{ t('skill.description') }}</span>
              <p>{{ detailSkill?.description }}</p>
            </div>
            <div v-if="detailSkill?.license">
              <span class="text-xs text-gray-500">{{ t('skill.license') }}</span>
              <p>{{ detailSkill?.license }}</p>
            </div>
            <div v-if="detailSkill?.location">
              <span class="text-xs text-gray-500">{{ t('skill.location') }}</span>
              <p class="text-sm truncate">{{ detailSkill?.location }}</p>
            </div>
          </div>
        </div>

        <!-- Instructions -->
        <div v-if="detailSkill?.instructions">
          <h4 class="text-sm font-medium mb-2">{{ t('skill.instructions') }}</h4>
          <pre class="bg-gray-50 rounded-lg p-4 text-sm whitespace-pre-wrap overflow-auto max-h-300">{{ detailSkill?.instructions }}</pre>
        </div>

        <!-- Resources -->
        <div v-if="detailSkill?.resources && detailSkill?.resources.length > 0">
          <h4 class="text-sm font-medium mb-2">{{ t('skill.resources') }} ({{ detailSkill?.resources.length }})</h4>
          <div class="space-y-2">
            <div v-for="resource in detailSkill?.resources" :key="resource.id" class="bg-gray-50 rounded-lg p-3">
              <div class="flex items-center justify-between">
                <div>
                  <el-tag size="small" :type="resource.type === 'script' ? 'warning' : resource.type === 'reference' ? 'info' : 'success'">
                    {{ resource.type }}
                  </el-tag>
                  <span class="ml-2 font-medium">{{ resource.name }}</span>
                </div>
                <span class="text-xs text-gray-400 truncate max-w-200">{{ resource.path }}</span>
              </div>
              <div v-if="resource.content" class="mt-2">
                <pre class="text-xs bg-white rounded p-2 overflow-auto max-h-150 whitespace-pre-wrap">{{ resource.content.slice(0, 500) }}{{ resource.content.length > 500 ? '...' : '' }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="activateInChat(detailSkill)">{{ t('skill.activate') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessageBox } from '@/plugins/element-plus-services'
import { Plus, Search, Loading } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useSkillsStore } from '@/stores/skills'
import type { Skill, CreateSkillRequest, UpdateSkillRequest } from '@/types/skill'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const router = useRouter()
const skillsStore = useSkillsStore()

const dialogVisible = ref(false)
const showScanDialog = ref(false)
const detailDialogVisible = ref(false)
const detailSkill = ref<Skill | null>(null)
const isEdit = ref(false)
const selectedSkill = ref<Skill | null>(null)
const formRef = ref<FormInstance>()
const submitting = ref(false)
const isMobile = ref(false)

// Scan dialog state
const scanPath = ref('')
const scanning = ref(false)
const scannedSkills = ref<Skill[]>([])

// Example skill state
const addingExample = ref(false)

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  skillsStore.loadSkills()
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

const form = reactive({
  name: '',
  display_name: '',
  description: '',
  instructions: '',
  license: '',
  allowed_tools: ''
})

const rules: FormRules = {
  name: [
    { required: true, message: 'Name is required', trigger: 'blur' },
    { pattern: /^[a-z][a-z0-9-]*$/, message: 'Name must be lowercase with hyphens', trigger: 'blur' }
  ],
  description: [{ required: true, message: 'Description is required', trigger: 'blur' }]
}

const resetForm = () => {
  form.name = ''
  form.display_name = ''
  form.description = ''
  form.instructions = ''
  form.license = ''
  form.allowed_tools = ''
}

const openCreateDialog = () => {
  isEdit.value = false
  selectedSkill.value = null
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = (skill: Skill) => {
  isEdit.value = true
  selectedSkill.value = skill
  form.name = skill.name
  form.display_name = skill.display_name || ''
  form.description = skill.description
  form.instructions = skill.instructions || ''
  form.license = skill.license || ''
  form.allowed_tools = skill.allowed_tools || ''
  dialogVisible.value = true
}

const openDetailDialog = async (skill: Skill) => {
  // Fetch full skill details with resources
  try {
    const response = await skillsStore.skills.find(s => s.id === skill.id)
    if (response) {
      detailSkill.value = response
    } else {
      detailSkill.value = skill
    }
  } catch {
    detailSkill.value = skill
  }
  detailDialogVisible.value = true
}

const activateInChat = (skill: Skill | null) => {
  if (!skill) return
  detailDialogVisible.value = false
  // Navigate to chat page with skill activation
  router.push({
    path: '/chat',
    query: { activateSkill: skill.name }
  })
}

const submitForm = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    if (isEdit.value && selectedSkill.value) {
      const data: UpdateSkillRequest = {
        display_name: form.display_name,
        description: form.description,
        instructions: form.instructions,
        license: form.license,
        allowed_tools: form.allowed_tools
      }
      await skillsStore.updateSkill(selectedSkill.value.id, data)
    } else {
      const data: CreateSkillRequest = {
        name: form.name,
        display_name: form.display_name,
        description: form.description,
        instructions: form.instructions,
        license: form.license,
        allowed_tools: form.allowed_tools,
        source: 'database',
        enabled: true
      }
      await skillsStore.createSkill(data)
    }
    dialogVisible.value = false
    await skillsStore.loadCatalog()
  } finally {
    submitting.value = false
  }
}

const toggleEnabled = async (skill: Skill) => {
  await skillsStore.toggleSkill(skill.id)
  await skillsStore.loadCatalog()
}

const deleteSkill = async (skill: Skill) => {
  try {
    await ElMessageBox.confirm(t('common.confirmDelete'), t('common.confirm'), { type: 'warning' })
    await skillsStore.deleteSkill(skill.id)
    await skillsStore.loadCatalog()
  } catch {
    // User cancelled
  }
}

const scanSkills = async () => {
  scanning.value = true
  try {
    scannedSkills.value = await skillsStore.scanLocalSkills(scanPath.value || undefined)
  } finally {
    scanning.value = false
  }
}

const importSkill = async (skill: Skill) => {
  if (skill.location) {
    const imported = await skillsStore.importSkill(skill.location)
    if (imported) {
      scannedSkills.value = scannedSkills.value.filter(s => s.name !== skill.name)
      await skillsStore.loadCatalog()
    }
  }
}

const addExampleSkill = async () => {
  addingExample.value = true
  try {
    const exampleSkill: CreateSkillRequest = {
      name: 'code-review',
      display_name: '代码审查',
      description: '帮助审查代码质量、发现潜在问题、提供改进建议。当用户需要审查代码或讨论代码质量时使用此技能。',
      instructions: `# 代码审查技能

## 使用场景
当用户请求审查代码、检查代码质量或询问改进建议时激活此技能。

## 审查要点

### 1. 代码质量
- 检查命名规范（变量、函数、类名是否清晰）
- 检查代码结构是否合理
- 检查是否有重复代码

### 2. 潜在问题
- 检查是否有安全漏洞（如SQL注入、XSS）
- 检查是否有性能问题
- 检查是否有边界条件遗漏

### 3. 最佳实践
- 建议遵循的语言/框架最佳实践
- 建议的错误处理方式
- 建议的测试策略

## 输出格式

### 使用 Diff 格式展示修改建议

审查结果中，对于需要修改的代码，必须使用 **diff 格式** 展示：

\`\`\`diff
- // 原代码（需要删除/修改的部分）
+ // 新代码（建议添加/替换的部分）
\`\`\`

示例：

\`\`\`diff
- const name = user.name;
+ const userName = user.displayName || user.name;
\`\`\`

### 完整审查报告结构

1. **问题列表**（按严重程度分类）
   - 🔴 严重：安全漏洞、逻辑错误
   - 🟠 中等：性能问题、代码异味
   - 🟡 轻微：命名不规范、可读性问题

2. **改进建议**（使用 diff 格式）

3. **优化后的完整代码**（如有必要）
`,
      license: 'MIT',
      source: 'database',
      enabled: true
    }
    await skillsStore.createSkill(exampleSkill)
    await skillsStore.loadCatalog()
  } finally {
    addingExample.value = false
  }
}
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: #9ca3af;
}

.w-full {
  width: 100%;
}

.max-h-300 {
  max-height: 300px;
}

.max-h-150 {
  max-height: 150px;
}

.max-w-200 {
  max-width: 200px;
}

.truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.whitespace-pre-wrap {
  white-space: pre-wrap;
}
</style>
