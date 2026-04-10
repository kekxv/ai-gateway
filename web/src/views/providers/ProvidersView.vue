<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('provider.title') }}</h2>
      <el-button type="primary" @click="openCreateDialog">
        {{ t('common.create') }}
      </el-button>
    </div>

    <!-- Card Grid -->
    <div v-if="loading" class="text-center py-12">
      <el-icon class="is-loading" :size="40"><Loading /></el-icon>
    </div>
    <div v-else-if="providers.length === 0" class="text-center py-12 text-gray-500">
      {{ t('common.noData') }}
    </div>
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      <div
        v-for="provider in paginatedProviders"
        :key="provider.id"
        class="bg-white rounded-lg shadow-sm border border-gray-100 p-4 hover:shadow-md transition-shadow"
      >
        <!-- Header: Name + Status -->
        <div class="flex items-center justify-between mb-3">
          <h3 class="font-semibold text-gray-800 truncate">{{ provider.name }}</h3>
          <el-tag :type="provider.disabled ? 'danger' : 'success'" size="small">
            {{ provider.disabled ? t('common.disabled') : t('common.enabled') }}
          </el-tag>
        </div>

        <!-- Types with BaseURLs -->
        <div class="mb-3 space-y-2">
          <template v-if="provider.providerTypes && provider.providerTypes.length > 0">
            <div
              v-for="pt in provider.providerTypes"
              :key="getPtType(pt)"
              class="flex items-center gap-2 text-sm"
            >
              <el-tag size="small" effect="plain">{{ getPtType(pt) }}</el-tag>
              <span class="text-gray-500 truncate flex-1" :title="getPtBaseURL(pt)">{{ getPtBaseURL(pt) }}</span>
            </div>
          </template>
          <template v-else>
            <div class="flex items-center gap-2 text-sm">
              <el-tag size="small" effect="plain">{{ provider.type || 'openai' }}</el-tag>
              <span class="text-gray-500 truncate flex-1">{{ provider.base_url || provider.baseURL }}</span>
            </div>
          </template>
        </div>

        <!-- Auto Load Models -->
        <div class="flex items-center gap-2 mb-3">
          <span class="text-xs text-gray-400">{{ t('provider.autoLoadModels') }}</span>
          <el-tag :type="(provider.auto_load_models || provider.autoLoadModels) ? 'success' : 'info'" size="small">
            {{ (provider.auto_load_models || provider.autoLoadModels) ? t('common.yes') : t('common.no') }}
          </el-tag>
        </div>

        <!-- Actions -->
        <div class="flex flex-wrap gap-2 pt-3 border-t border-gray-100">
          <el-button size="small" link type="primary" @click="openEditDialog(provider)">
            {{ t('common.edit') }}
          </el-button>
          <el-button size="small" link type="success" @click="openModelsDialog(provider)">
            {{ t('provider.loadModels') }}
          </el-button>
          <el-button size="small" link :type="provider.disabled ? 'warning' : 'info'" @click="toggleDisabled(provider)">
            {{ provider.disabled ? t('common.enabled') : t('common.disabled') }}
          </el-button>
          <el-button size="small" link type="danger" @click="deleteProvider(provider)">
            {{ t('common.delete') }}
          </el-button>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="providers.length > 0" class="flex justify-center mt-6">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[12, 24, 48, 96]"
        layout="total, sizes, prev, pager, next"
        :size="isMobile ? 'small' : 'default'"
      />
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? t('provider.editTitle') : t('provider.createTitle')" :width="isMobile ? '90%' : '600px'">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" label-position="top">
        <el-form-item :label="t('provider.name')" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="t('provider.type')" prop="typesList">
          <el-select v-model="form.typesList" multiple class="w-full" placeholder="Select provider types" @change="handleTypesChange">
            <el-option label="OpenAI" value="openai" />
            <el-option label="Anthropic/Claude" value="anthropic" />
            <el-option label="Gemini" value="gemini" />
            <el-option label="Custom" value="custom" />
          </el-select>
        </el-form-item>
        <!-- Type-specific Base URLs -->
        <div v-for="typeName in form.typesList" :key="typeName" class="mb-4">
          <el-form-item :label="typeName + ' Base URL'">
            <el-input
              v-model="form.providerTypeMap[typeName]"
              :placeholder="getDefaultBaseURL(typeName)"
            >
              <template #prepend>
                <el-tag size="small">{{ typeName }}</el-tag>
              </template>
            </el-input>
          </el-form-item>
        </div>
        <el-form-item label="API Key" prop="api_key">
          <el-input v-model="form.api_key" type="password" show-password />
        </el-form-item>
        <el-form-item :label="t('provider.autoLoadModels')" prop="auto_load_models">
          <el-switch v-model="form.auto_load_models" />
        </el-form-item>
        <el-form-item :label="t('common.disabled')" prop="disabled">
          <el-switch v-model="form.disabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- Models Selection Dialog -->
    <el-dialog v-model="modelsDialogVisible" title="选择要添加的模型" :width="isMobile ? '95%' : '800px'">
      <div v-if="loadingModels" class="text-center py-8">
        <el-icon class="is-loading" :size="40"><Loading /></el-icon>
        <p class="mt-4 text-gray-500">正在加载模型列表...</p>
      </div>
      <div v-else-if="modelsError" class="text-center py-8">
        <el-alert type="error" :title="modelsError" show-icon />
      </div>
      <div v-else-if="availableModels.length > 0">
        <div class="mb-4">
          <el-input v-model="modelSearchTerm" placeholder="搜索模型..." clearable>
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
        <div class="flex items-center justify-between mb-4 px-1">
          <el-checkbox v-model="selectAllModels" @change="handleSelectAll">全选</el-checkbox>
          <span class="text-sm text-gray-500 whitespace-nowrap">已选择 {{ selectedModels.size }} / {{ filteredModels.length }}</span>
        </div>
        <div class="max-h-80 overflow-y-auto border rounded-lg">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 p-2">
            <div
              v-for="model in filteredModels"
              :key="model.id"
              class="p-3 border rounded-lg cursor-pointer transition-all hover:shadow-sm flex items-center gap-3"
              :class="selectedModels.has(model.name) ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 bg-white'"
              @click="toggleModelSelection(model.name)"
            >
              <el-checkbox :model-value="selectedModels.has(model.name)" @click.stop />
              <div class="flex-1 min-w-0">
                <p class="font-medium text-gray-800 text-sm truncate">{{ model.name }}</p>
                <p v-if="model.description" class="text-xs text-gray-500 truncate">{{ model.description }}</p>
              </div>
              <el-tag v-if="model.exists" size="small" type="success">已添加</el-tag>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="text-center py-8 text-gray-500">
        未找到模型
      </div>
      <template #footer>
        <el-button @click="modelsDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button
          type="primary"
          :loading="savingModels"
          :disabled="selectedModels.size === 0"
          @click="saveSelectedModels"
        >
          {{ savingModels ? '保存中...' : `添加 ${selectedModels.size} 个模型` }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, Search } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { providerApi } from '@/api/provider'
import { modelApi } from '@/api/model'
import type { Provider } from '@/types/provider'

const { t } = useI18n()
const loading = ref(false)
const submitting = ref(false)
const providers = ref<Provider[]>([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const selectedProvider = ref<Provider | null>(null)
const formRef = ref<FormInstance>()
const isMobile = ref(false)

// Check if mobile on mount and resize
const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  fetchProviders()
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

// Models dialog
const modelsDialogVisible = ref(false)
const loadingModels = ref(false)
const savingModels = ref(false)
const modelsError = ref('')
const availableModels = ref<{ id: string; name: string; description?: string; exists?: boolean }[]>([])
const selectedModels = ref<Set<string>>(new Set())
const modelSearchTerm = ref('')
const currentProviderId = ref<number | null>(null)
const existingModelNames = ref<Set<string>>(new Set())

const pagination = reactive({
  page: 1,
  pageSize: 12,
  total: 0
})

const form = reactive({
  name: '',
  base_url: '',
  typesList: [] as string[],
  providerTypeMap: {} as Record<string, string>,
  auto_load_models: false,
  disabled: false,
  api_key: ''
})

const rules: FormRules = {
  name: [{ required: true, message: 'Name is required', trigger: 'blur' }]
}

const filteredModels = computed(() => {
  if (!modelSearchTerm.value) return availableModels.value
  const term = modelSearchTerm.value.toLowerCase()
  return availableModels.value.filter(m =>
    m.name.toLowerCase().includes(term) ||
    (m.description && m.description.toLowerCase().includes(term))
  )
})

const selectAllModels = computed({
  get: () => filteredModels.value.length > 0 && selectedModels.value.size === filteredModels.value.length,
  set: () => {}
})

// Frontend pagination slicing
const paginatedProviders = computed(() => {
  const start = (pagination.page - 1) * pagination.pageSize
  const end = start + pagination.pageSize
  return providers.value.slice(start, end)
})

const fetchProviders = async () => {
  loading.value = true
  try {
    const response = await providerApi.list()
    providers.value = response.data || []
    pagination.total = providers.value.length
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.name = ''
  form.base_url = ''
  form.typesList = ['openai']
  form.providerTypeMap = { openai: '' }
  form.auto_load_models = false
  form.disabled = false
  form.api_key = ''
}

const getDefaultBaseURL = (typeName: string): string => {
  const defaults: Record<string, string> = {
    openai: 'https://api.openai.com/v1',
    anthropic: 'https://api.anthropic.com/v1',
    gemini: 'https://generativelanguage.googleapis.com/v1beta',
    custom: ''
  }
  return defaults[typeName] || ''
}

// Helper functions to handle both camelCase and PascalCase field names
const getPtType = (pt: { type?: string; Type?: string }) => pt.type || pt.Type || ''
const getPtBaseURL = (pt: { baseURL?: string; BaseURL?: string }) => pt.baseURL || pt.BaseURL || ''

const handleTypesChange = (types: string[]) => {
  // Initialize providerTypeMap for new types
  for (const t of types) {
    if (!(t in form.providerTypeMap)) {
      form.providerTypeMap[t] = ''
    }
  }
  // Remove entries for unselected types
  const typeSet = new Set(types)
  for (const key of Object.keys(form.providerTypeMap)) {
    if (!typeSet.has(key)) {
      delete form.providerTypeMap[key]
    }
  }
}

const openCreateDialog = () => {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = (provider: Provider) => {
  isEdit.value = true
  selectedProvider.value = provider
  form.name = provider.name
  form.typesList = provider.typesList || (provider.type ? [provider.type] : ['openai'])
  form.auto_load_models = provider.auto_load_models ?? provider.autoLoadModels ?? false
  form.disabled = provider.disabled ?? false
  form.api_key = ''
  // Initialize providerTypeMap from providerTypes
  form.providerTypeMap = {}
  if (provider.providerTypes && provider.providerTypes.length > 0) {
    for (const pt of provider.providerTypes) {
      form.providerTypeMap[getPtType(pt)] = getPtBaseURL(pt)
    }
  } else {
    // Fallback to default baseURL for all types
    const defaultBaseURL = provider.base_url ?? provider.baseURL ?? ''
    for (const t of form.typesList) {
      form.providerTypeMap[t] = defaultBaseURL
    }
  }
  dialogVisible.value = true
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
    // Build providerTypes array from providerTypeMap
    const providerTypes = form.typesList
      .filter(t => form.providerTypeMap[t])
      .map(t => ({
        type: t,
        baseURL: form.providerTypeMap[t] || getDefaultBaseURL(t)
      }))

    if (isEdit.value && selectedProvider.value) {
      await providerApi.update(selectedProvider.value.id, {
        name: form.name,
        typesList: form.typesList,
        providerTypes,
        auto_load_models: form.auto_load_models,
        disabled: form.disabled,
        api_key: form.api_key || undefined
      })
    } else {
      await providerApi.create({
        name: form.name,
        typesList: form.typesList,
        providerTypes,
        auto_load_models: form.auto_load_models,
        disabled: form.disabled,
        api_key: form.api_key
      })
    }
    ElMessage.success(t('common.success'))
    dialogVisible.value = false
    fetchProviders()
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    submitting.value = false
  }
}

const openModelsDialog = async (provider: Provider) => {
  currentProviderId.value = provider.id
  modelsDialogVisible.value = true
  loadingModels.value = true
  modelsError.value = ''
  availableModels.value = []
  selectedModels.value = new Set()
  existingModelNames.value = new Set()

  try {
    // Fetch available models from provider
    const response = await providerApi.loadModels(provider.id)
    const models = response.data || []

    // Fetch existing models from database
    try {
      const existingResponse = await modelApi.list()
      const existingModels = existingResponse.data || []
      existingModelNames.value = new Set(existingModels.map((m: { name: string }) => m.name))
    } catch {
      // Ignore error when fetching existing models
    }

    // Mark models that already exist
    availableModels.value = models.map((m: { id: string; name: string; description?: string }) => ({
      ...m,
      exists: existingModelNames.value.has(m.name)
    }))
  } catch (error: unknown) {
    const err = error as { response?: { data?: { error?: string } } }
    modelsError.value = err.response?.data?.error || '获取模型列表失败'
  } finally {
    loadingModels.value = false
  }
}

const handleSelectAll = (checked: boolean) => {
  if (checked) {
    selectedModels.value = new Set(filteredModels.value.map(m => m.name))
  } else {
    selectedModels.value = new Set()
  }
}

const toggleModelSelection = (modelName: string) => {
  const newSelection = new Set(selectedModels.value)
  if (newSelection.has(modelName)) {
    newSelection.delete(modelName)
  } else {
    newSelection.add(modelName)
  }
  selectedModels.value = newSelection
}

const saveSelectedModels = async () => {
  if (!currentProviderId.value || selectedModels.value.size === 0) return

  savingModels.value = true
  try {
    const modelsToSave = availableModels.value
      .filter(m => selectedModels.value.has(m.name))
      .map(m => ({ name: m.name, description: m.description || '' }))

    await providerApi.addModels(currentProviderId.value, { models: modelsToSave })
    ElMessage.success(`成功添加 ${modelsToSave.length} 个模型`)
    modelsDialogVisible.value = false
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    savingModels.value = false
  }
}

const toggleDisabled = async (provider: Provider) => {
  const action = provider.disabled ? '启用' : '禁用'
  try {
    await ElMessageBox.confirm(`确定要${action}此提供商吗？`, t('common.confirm'), { type: 'warning' })
    await providerApi.update(provider.id, {
      disabled: !provider.disabled
    })
    ElMessage.success(t('common.success'))
    fetchProviders()
  } catch {
    // User cancelled
  }
}

const deleteProvider = async (provider: Provider) => {
  try {
    await ElMessageBox.confirm(t('common.confirmDelete'), t('common.confirm'), { type: 'warning' })
    await providerApi.delete(provider.id)
    ElMessage.success(t('common.success'))
    fetchProviders()
  } catch {
    // User cancelled
  }
}
</script>