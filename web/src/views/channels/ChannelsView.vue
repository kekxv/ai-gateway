<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('channel.title') }}</h2>
      <el-button type="primary" @click="openCreateDialog">
        {{ t('common.create') }}
      </el-button>
    </div>

    <!-- Cards Grid -->
    <div v-loading="loading" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="channel in paginatedChannels"
        :key="channel.id"
        class="bg-white rounded-xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
      >
        <div class="p-4">
          <!-- Header -->
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-semibold text-gray-800 truncate">{{ channel.name }}</h3>
            <div class="flex items-center gap-1">
              <el-tag :type="channel.enabled ? 'success' : 'danger'" size="small">
                {{ channel.enabled ? t('common.enabled') : t('common.disabled') }}
              </el-tag>
              <el-tag v-if="channel.shared" type="info" size="small">{{ t('channel.shared') }}</el-tag>
            </div>
          </div>

          <!-- Providers -->
          <div class="mb-3">
            <div class="text-xs text-gray-500 mb-1">Providers</div>
            <div class="flex flex-wrap gap-1">
              <el-tag v-for="p in channel.providers?.slice(0, 3)" :key="p.id" size="small" type="info" class="max-w-[100px] overflow-hidden">
                <span class="truncate block">{{ p.name }}</span>
              </el-tag>
              <el-tag v-if="(channel.providers?.length || 0) > 3" size="small" type="info">
                +{{ channel.providers!.length - 3 }}
              </el-tag>
              <span v-if="!channel.providers?.length" class="text-gray-400 text-sm">-</span>
            </div>
          </div>

          <!-- Models -->
          <div class="mb-3">
            <div class="text-xs text-gray-500 mb-1">Models</div>
            <div class="flex flex-wrap gap-1">
              <el-tag v-for="m in channel.allowedModels?.slice(0, 4)" :key="m.id" size="small" class="!max-w-[140px] overflow-hidden">
                <span class="truncate block">{{ m.name }}</span>
              </el-tag>
              <el-tag v-if="(channel.allowedModels?.length || 0) > 4" size="small">
                +{{ channel.allowedModels!.length - 4 }}
              </el-tag>
              <span v-if="!channel.allowedModels?.length" class="text-gray-400 text-sm">-</span>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center justify-between pt-3 border-t border-gray-100">
            <span class="text-xs text-gray-400">{{ formatDate(channel.createdAt) }}</span>
            <el-dropdown trigger="click">
              <el-button size="small">
                操作 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="openEditDialog(channel)">{{ t('common.edit') }}</el-dropdown-item>
                  <el-dropdown-item @click="toggleEnabled(channel)">
                    {{ channel.enabled ? 'Disable' : 'Enable' }}
                  </el-dropdown-item>
                  <el-dropdown-item divided @click="deleteChannel(channel)">{{ t('common.delete') }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-if="!loading && paginatedChannels.length === 0" class="col-span-full text-center py-12 text-gray-500">
        No channels found. Click "Create" to add one.
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="pagination.total > pagination.pageSize" class="flex justify-center">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[10, 20, 50]"
        layout="prev, pager, next"
      />
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? t('channel.editTitle') : t('channel.createTitle')" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item :label="t('channel.name')" prop="name">
          <el-input v-model="form.name" placeholder="Enter channel name" />
        </el-form-item>

        <el-form-item label="Providers" prop="provider_ids">
          <el-select v-model="form.provider_ids" multiple placeholder="Select providers" class="w-full">
            <el-option v-for="p in providers" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="Models">
          <div class="w-full">
            <div class="flex items-center justify-between mb-2">
              <el-input v-model="modelSearch" placeholder="Search models..." clearable class="w-40" size="small">
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
              </el-input>
              <el-checkbox v-model="selectAllModels" @change="handleSelectAllModels">Select All</el-checkbox>
            </div>
            <div class="max-h-48 overflow-y-auto border rounded-lg p-2">
              <div class="grid grid-cols-2 gap-1">
                <div
                  v-for="model in filteredModels"
                  :key="model.id"
                  class="p-2 border rounded cursor-pointer transition-all hover:border-indigo-300 flex items-center gap-2 text-sm"
                  :class="form.model_ids.includes(model.id) ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 bg-white'"
                  @click="toggleModel(model.id)"
                >
                  <el-checkbox :model-value="form.model_ids.includes(model.id)" @click.stop size="small" />
                  <span class="truncate">{{ model.name }}</span>
                </div>
              </div>
            </div>
            <div class="text-xs text-gray-500 mt-1">Selected: {{ form.model_ids.length }}</div>
          </div>
        </el-form-item>

        <el-form-item :label="t('channel.shared')">
          <el-switch v-model="form.shared" />
        </el-form-item>

        <el-form-item :label="t('common.enabled')">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, ArrowDown } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { channelApi } from '@/api/channel'
import { providerApi } from '@/api/provider'
import { modelApi } from '@/api/model'
import type { Channel } from '@/types/channel'
import type { Provider } from '@/types/provider'
import type { Model } from '@/types/model'
import dayjs from 'dayjs'

const { t } = useI18n()
const loading = ref(false)
const submitting = ref(false)
const channels = ref<Channel[]>([])
const providers = ref<Provider[]>([])
const models = ref<Model[]>([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const selectedChannel = ref<Channel | null>(null)
const formRef = ref<FormInstance>()
const modelSearch = ref('')

const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
})

const form = reactive({
  name: '',
  provider_ids: [] as number[],
  model_ids: [] as number[],
  enabled: true,
  shared: false
})

const rules: FormRules = {
  name: [{ required: true, message: 'Name is required', trigger: 'blur' }],
  provider_ids: [{ required: true, message: 'At least one provider is required', trigger: 'change', type: 'array', min: 1 }]
}

const filteredModels = computed(() => {
  if (!modelSearch.value) return models.value
  const term = modelSearch.value.toLowerCase()
  return models.value.filter(m => m.name.toLowerCase().includes(term))
})

const selectAllModels = computed({
  get: () => filteredModels.value.length > 0 && form.model_ids.length === filteredModels.value.length,
  set: () => {}
})

// Frontend pagination slicing
const paginatedChannels = computed(() => {
  const start = (pagination.page - 1) * pagination.pageSize
  const end = start + pagination.pageSize
  return channels.value.slice(start, end)
})

const formatDate = (date: string) => dayjs(date).format('YYYY-MM-DD')

const handleSelectAllModels = (checked: boolean) => {
  if (checked) {
    form.model_ids = filteredModels.value.map(m => m.id)
  } else {
    form.model_ids = []
  }
}

const toggleModel = (modelId: number) => {
  const index = form.model_ids.indexOf(modelId)
  if (index > -1) {
    form.model_ids.splice(index, 1)
  } else {
    form.model_ids.push(modelId)
  }
}

const fetchChannels = async () => {
  loading.value = true
  try {
    const response = await channelApi.list()
    channels.value = response.data || []
    pagination.total = channels.value.length
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

const fetchModels = async () => {
  try {
    const response = await modelApi.list()
    models.value = response.data || []
  } catch (error) {
    console.error('Failed to fetch models')
  }
}

const resetForm = () => {
  form.name = ''
  form.provider_ids = []
  form.model_ids = []
  form.enabled = true
  form.shared = false
  modelSearch.value = ''
}

const openCreateDialog = () => {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = (channel: Channel) => {
  isEdit.value = true
  selectedChannel.value = channel
  form.name = channel.name
  form.provider_ids = channel.providers?.map(p => p.id) || []
  form.model_ids = channel.allowedModels?.map(m => m.id) || channel.models?.map(m => typeof m === 'object' ? m.id : m) || []
  form.enabled = channel.enabled
  form.shared = channel.shared
  modelSearch.value = ''
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
    if (isEdit.value && selectedChannel.value) {
      await channelApi.update(selectedChannel.value.id, {
        name: form.name,
        enabled: form.enabled,
        shared: form.shared
      })
      if (form.provider_ids.length > 0) {
        await channelApi.bindProviders(selectedChannel.value.id, form.provider_ids)
      }
      if (form.model_ids.length > 0) {
        await channelApi.bindModels(selectedChannel.value.id, form.model_ids)
      }
    } else {
      const response = await channelApi.create({
        name: form.name,
        enabled: form.enabled,
        shared: form.shared
      })
      const channelId = response.data.id
      if (form.provider_ids.length > 0) {
        await channelApi.bindProviders(channelId, form.provider_ids)
      }
      if (form.model_ids.length > 0) {
        await channelApi.bindModels(channelId, form.model_ids)
      }
    }
    ElMessage.success(t('common.success'))
    dialogVisible.value = false
    fetchChannels()
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    submitting.value = false
  }
}

const toggleEnabled = async (channel: Channel) => {
  const action = channel.enabled ? 'Disable' : 'Enable'
  try {
    await ElMessageBox.confirm(`Are you sure you want to ${action.toLowerCase()} this channel?`, t('common.confirm'), { type: 'warning' })
    await channelApi.update(channel.id, { enabled: !channel.enabled })
    ElMessage.success(t('common.success'))
    fetchChannels()
  } catch {
    // User cancelled
  }
}

const deleteChannel = async (channel: Channel) => {
  try {
    await ElMessageBox.confirm(t('common.confirmDelete'), t('common.confirm'), { type: 'warning' })
    await channelApi.delete(channel.id)
    ElMessage.success(t('common.success'))
    fetchChannels()
  } catch {
    // User cancelled
  }
}

onMounted(() => {
  fetchChannels()
  fetchProviders()
  fetchModels()
})
</script>