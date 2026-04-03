<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('provider.title') }}</h2>
      <el-button type="primary" @click="openCreateDialog">
        {{ t('common.create') }}
      </el-button>
    </div>

    <!-- Table -->
    <el-card>
      <el-table :data="providers" stripe v-loading="loading">
        <el-table-column prop="name" :label="t('provider.name')" />
        <el-table-column prop="base_url" :label="t('provider.baseURL')" />
        <el-table-column prop="type" :label="t('provider.type')" width="120">
          <template #default="{ row }">
            <el-tag>{{ row.type || 'custom' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="auto_load_models" :label="t('provider.autoLoadModels')" width="140">
          <template #default="{ row }">
            <el-tag :type="row.auto_load_models ? 'success' : 'info'">
              {{ row.auto_load_models ? t('common.yes') : t('common.no') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="disabled" :label="t('common.status')" width="100">
          <template #default="{ row }">
            <el-tag :type="row.disabled ? 'danger' : 'success'">
              {{ row.disabled ? t('common.disabled') : t('common.enabled') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="320" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEditDialog(row)">{{ t('common.edit') }}</el-button>
            <el-button size="small" type="success" @click="openModelsDialog(row)">{{ t('provider.loadModels') }}</el-button>
            <el-button size="small" :type="row.disabled ? 'warning' : 'info'" @click="toggleDisabled(row)">
              {{ row.disabled ? t('common.enabled') : t('common.disabled') }}
            </el-button>
            <el-button size="small" type="danger" @click="deleteProvider(row)">{{ t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <div class="flex justify-end mt-4">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @change="fetchProviders"
        />
      </div>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? t('provider.editTitle') : t('provider.createTitle')" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item :label="t('provider.name')" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="t('provider.baseURL')" prop="base_url">
          <el-input v-model="form.base_url" placeholder="https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item :label="t('provider.type')" prop="type">
          <el-select v-model="form.type">
            <el-option label="OpenAI" value="openai" />
            <el-option label="Gemini" value="gemini" />
            <el-option label="Custom" value="custom" />
          </el-select>
        </el-form-item>
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
    <el-dialog v-model="modelsDialogVisible" title="选择要添加的模型" width="800px">
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
          <div class="grid grid-cols-2 gap-2 p-2">
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
import { ref, reactive, computed, onMounted } from 'vue'
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
  pageSize: 10,
  total: 0
})

const form = reactive({
  name: '',
  base_url: '',
  type: 'openai',
  auto_load_models: false,
  disabled: false,
  api_key: ''
})

const rules: FormRules = {
  name: [{ required: true, message: 'Name is required', trigger: 'blur' }],
  base_url: [{ required: true, message: 'Base URL is required', trigger: 'blur' }],
  type: [{ required: true, message: 'Type is required', trigger: 'change' }]
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

const fetchProviders = async () => {
  loading.value = true
  try {
    const response = await providerApi.list({
      page: pagination.page,
      page_size: pagination.pageSize
    })
    providers.value = response.data.providers || response.data
    pagination.total = response.data.total || providers.value.length
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.name = ''
  form.base_url = ''
  form.type = 'openai'
  form.auto_load_models = false
  form.disabled = false
  form.api_key = ''
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
  form.base_url = provider.base_url ?? provider.baseURL ?? ''
  form.type = provider.type || 'openai'
  form.auto_load_models = provider.auto_load_models ?? provider.autoLoadModels ?? false
  form.disabled = provider.disabled ?? false
  form.api_key = ''
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
    if (isEdit.value && selectedProvider.value) {
      await providerApi.update(selectedProvider.value.id, {
        name: form.name,
        base_url: form.base_url,
        type: form.type,
        auto_load_models: form.auto_load_models,
        disabled: form.disabled,
        api_key: form.api_key || undefined
      })
    } else {
      await providerApi.create({
        name: form.name,
        base_url: form.base_url,
        type: form.type,
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
      const existingResponse = await modelApi.list({ page: 1, page_size: 1000 })
      const existingModels = existingResponse.data.models || existingResponse.data || []
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
    const modelsToSave = availableModels.value.filter(m => selectedModels.value.has(m.name))

    for (const model of modelsToSave) {
      try {
        await modelApi.create({
          name: model.name,
          description: model.description || ''
        })
      } catch {
        // Model may already exist, ignore error
      }
    }

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

onMounted(fetchProviders)
</script>