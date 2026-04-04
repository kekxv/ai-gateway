<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('model.title') }}</h2>
      <el-button type="primary" @click="openCreateDialog">
        {{ t('common.create') }}
      </el-button>
    </div>

    <!-- Search -->
    <div class="flex gap-4">
      <el-input
        v-model="searchTerm"
        placeholder="Search models..."
        clearable
        class="max-w-xs"
        @input="filterModels"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- Cards Grid -->
    <div v-loading="loading" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="model in paginatedModels"
        :key="model.id"
        class="bg-white rounded-xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
      >
        <div class="p-4">
          <!-- Header -->
          <div class="flex items-start justify-between mb-3">
            <div class="flex-1 min-w-0">
              <h3 class="font-semibold text-gray-800 truncate">{{ model.name }}</h3>
              <p v-if="model.alias" class="text-sm text-gray-500 truncate">{{ model.alias }}</p>
            </div>
            <el-tag v-if="model.modelRoutes?.length" type="success" size="small">
              {{ model.modelRoutes.length }} routes
            </el-tag>
          </div>

          <!-- Description -->
          <p v-if="model.description" class="text-sm text-gray-600 mb-3 line-clamp-2">
            {{ model.description }}
          </p>

          <!-- Pricing -->
          <div class="grid grid-cols-2 gap-2 mb-3">
            <div class="bg-gray-50 rounded-lg p-2">
              <div class="text-xs text-gray-500">Input Price</div>
              <div class="text-sm font-medium text-gray-800">{{ formatPrice(model.inputTokenPrice || model.input_price) }}</div>
            </div>
            <div class="bg-gray-50 rounded-lg p-2">
              <div class="text-xs text-gray-500">Output Price</div>
              <div class="text-sm font-medium text-gray-800">{{ formatPrice(model.outputTokenPrice || model.output_price) }}</div>
            </div>
          </div>

          <!-- Routes Preview -->
          <div v-if="model.modelRoutes?.length" class="mb-3">
            <div class="text-xs text-gray-500 mb-1">Providers</div>
            <div class="flex flex-wrap gap-1">
              <el-tag
                v-for="route in model.modelRoutes.slice(0, 3)"
                :key="route.id"
                size="small"
                :type="route.disabled ? 'danger' : 'info'"
                class="!max-w-[100px] overflow-hidden"
              >
                <span class="truncate block">{{ route.provider?.name || 'Unknown' }}</span>
              </el-tag>
              <el-tag v-if="model.modelRoutes.length > 3" size="small">
                +{{ model.modelRoutes.length - 3 }}
              </el-tag>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center justify-between pt-3 border-t border-gray-100">
            <span class="text-xs text-gray-400">{{ formatDate(model.createdAt || model.created_at) }}</span>
            <div class="flex gap-2">
              <el-button size="small" link type="primary" @click="openEditDialog(model)">
                {{ t('common.edit') }}
              </el-button>
              <el-button size="small" link type="info" @click="openRoutesDialog(model)">
                Routes
              </el-button>
              <el-button size="small" link type="danger" @click="deleteModel(model)">
                {{ t('common.delete') }}
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-if="!loading && paginatedModels.length === 0" class="col-span-full text-center py-12 text-gray-500">
        <p v-if="searchTerm">No models found matching "{{ searchTerm }}"</p>
        <p v-else>No models found. Click "Create" to add one.</p>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="filteredModels.length > pagination.pageSize" class="flex justify-center">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="filteredModels.length"
        :page-sizes="[12, 24, 48]"
        layout="prev, pager, next"
      />
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? t('model.editTitle') : t('model.createTitle')" width="500px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item :label="t('model.name')" prop="name">
          <el-input v-model="form.name" placeholder="e.g., gpt-4, claude-3-opus" />
        </el-form-item>
        <el-form-item :label="t('model.alias')">
          <el-input v-model="form.alias" placeholder="Optional alias" />
        </el-form-item>
        <el-form-item :label="t('model.description')">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="Model description" />
        </el-form-item>
        <el-form-item :label="t('model.inputPrice')">
          <el-input-number v-model="form.input_price" :precision="6" :step="0.001" :min="0" class="w-full" />
        </el-form-item>
        <el-form-item :label="t('model.outputPrice')">
          <el-input-number v-model="form.output_price" :precision="6" :step="0.001" :min="0" class="w-full" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- Routes Dialog -->
    <el-dialog v-model="routesDialogVisible" title="Model Routes" width="700px">
      <div class="mb-4">
        <p class="text-sm text-gray-500">Configure which providers handle requests for this model. Weight determines load balancing priority.</p>
      </div>

      <!-- Existing Routes -->
      <div v-if="routes.length" class="space-y-2 mb-4">
        <div
          v-for="(route, index) in routes"
          :key="index"
          class="flex items-center gap-3 p-3 bg-gray-50 rounded-lg"
        >
          <div class="flex-1">
            <div class="font-medium text-gray-800">{{ route.provider?.name || 'Provider #' + route.providerId }}</div>
            <div class="text-sm text-gray-500">Weight: {{ route.weight }}</div>
          </div>
          <el-input-number
            v-model="route.weight"
            :min="1"
            :max="100"
            size="small"
            class="w-24"
          />
          <el-switch
            v-model="route.disabled"
            active-text="Disabled"
            inactive-text="Enabled"
          />
          <el-button size="small" type="danger" link @click="removeRoute(index)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
      <div v-else class="text-center py-6 text-gray-400 mb-4">
        No routes configured. Add a provider below.
      </div>

      <!-- Add New Route -->
      <div class="border-t pt-4">
        <div class="text-sm font-medium text-gray-700 mb-2">Add Provider Route</div>
        <div class="flex gap-2 items-end">
          <el-select v-model="newRoute.providerId" placeholder="Select Provider" class="flex-1">
            <el-option v-for="p in providers" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <el-input-number v-model="newRoute.weight" :min="1" :max="100" placeholder="Weight" class="w-28" />
          <el-button type="primary" @click="addRoute">Add</el-button>
        </div>
      </div>

      <template #footer>
        <el-button @click="routesDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveRoutes" :loading="submitting">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Delete } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { modelApi } from '@/api/model'
import { providerApi } from '@/api/provider'
import type { Model, ModelRoute } from '@/types/model'
import type { Provider } from '@/types/provider'
import dayjs from 'dayjs'

const { t } = useI18n()
const loading = ref(false)
const submitting = ref(false)
const models = ref<Model[]>([])
const providers = ref<Provider[]>([])
const routes = ref<ModelRoute[]>([])
const dialogVisible = ref(false)
const routesDialogVisible = ref(false)
const isEdit = ref(false)
const selectedModel = ref<Model | null>(null)
const formRef = ref<FormInstance>()
const searchTerm = ref('')

const pagination = reactive({
  page: 1,
  pageSize: 12,
  total: 0
})

const form = reactive({
  name: '',
  alias: '',
  description: '',
  input_price: 0,
  output_price: 0
})

const newRoute = reactive({
  providerId: null as number | null,
  weight: 1
})

const rules: FormRules = {
  name: [{ required: true, message: 'Name is required', trigger: 'blur' }]
}

const filteredModels = computed(() => {
  let result = models.value
  if (searchTerm.value) {
    const term = searchTerm.value.toLowerCase()
    result = result.filter(m =>
      m.name.toLowerCase().includes(term) ||
      (m.alias?.toLowerCase().includes(term)) ||
      (m.description?.toLowerCase().includes(term))
    )
  }
  return result
})

// Frontend pagination slicing (applied after filtering)
const paginatedModels = computed(() => {
  const start = (pagination.page - 1) * pagination.pageSize
  const end = start + pagination.pageSize
  return filteredModels.value.slice(start, end)
})

const formatDate = (date: string | undefined) => date ? dayjs(date).format('YYYY-MM-DD') : '-'
const formatPrice = (price?: number) => {
  if (!price) return '$0.00'
  return '$' + (price / 10000).toFixed(4) + '/1K'
}

const filterModels = () => {
  // Reset to first page when search term changes
  pagination.page = 1
}

const fetchModels = async () => {
  loading.value = true
  try {
    const response = await modelApi.list()
    models.value = response.data || []
    pagination.total = models.value.length
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    loading.value = false
  }
}

const fetchProviders = async () => {
  try {
    const response = await providerApi.list()
    providers.value = response.data || []
  } catch (error) {
    console.error('Failed to fetch providers')
  }
}

const resetForm = () => {
  form.name = ''
  form.alias = ''
  form.description = ''
  form.input_price = 0
  form.output_price = 0
}

const openCreateDialog = () => {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = (model: Model) => {
  isEdit.value = true
  selectedModel.value = model
  form.name = model.name
  form.alias = model.alias || ''
  form.description = model.description || ''
  form.input_price = model.inputTokenPrice || model.input_price || 0
  form.output_price = model.outputTokenPrice || model.output_price || 0
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
    if (isEdit.value && selectedModel.value) {
      await modelApi.update(selectedModel.value.id, {
        name: form.name,
        alias: form.alias,
        description: form.description,
        input_price: form.input_price,
        output_price: form.output_price
      })
    } else {
      await modelApi.create({
        name: form.name,
        alias: form.alias,
        description: form.description,
        input_price: form.input_price,
        output_price: form.output_price
      })
    }
    ElMessage.success(t('common.success'))
    dialogVisible.value = false
    fetchModels()
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    submitting.value = false
  }
}

const openRoutesDialog = async (model: Model) => {
  selectedModel.value = model
  try {
    const response = await modelApi.getRoutes(model.id)
    routes.value = response.data.routes || response.data || []
    // Add provider info to routes
    routes.value = routes.value.map(r => {
      const provider = providers.value.find(p => p.id === r.providerId || p.id === r.provider_id)
      return { ...r, provider }
    })
    routesDialogVisible.value = true
  } catch (error) {
    ElMessage.error(t('common.error'))
  }
}

const addRoute = () => {
  if (!newRoute.providerId) {
    ElMessage.warning('Please select a provider')
    return
  }
  const provider = providers.value.find(p => p.id === newRoute.providerId)
  routes.value.push({
    id: 0,
    modelId: selectedModel.value?.id || 0,
    channelId: 0,
    providerId: newRoute.providerId,
    provider,
    modelName: selectedModel.value?.name || '',
    weight: newRoute.weight,
    disabled: false,
    disabledUntil: null
  })
  newRoute.providerId = null
  newRoute.weight = 1
}

const removeRoute = (index: number) => {
  routes.value.splice(index, 1)
}

const saveRoutes = async () => {
  if (!selectedModel.value) return
  submitting.value = true
  try {
    await modelApi.updateRoutes(selectedModel.value.id, routes.value)
    ElMessage.success(t('common.success'))
    routesDialogVisible.value = false
    fetchModels()
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    submitting.value = false
  }
}

const deleteModel = async (model: Model) => {
  try {
    await ElMessageBox.confirm(t('common.confirmDelete'), t('common.confirm'), { type: 'warning' })
    await modelApi.delete(model.id)
    ElMessage.success(t('common.success'))
    fetchModels()
  } catch {
    // User cancelled
  }
}

onMounted(() => {
  fetchModels()
  fetchProviders()
})
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>