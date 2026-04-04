<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('apiKey.title') }}</h2>
      <el-button type="primary" @click="openCreateDialog">
        {{ t('common.create') }}
      </el-button>
    </div>

    <!-- Table -->
    <el-card>
      <el-table :data="paginatedKeys" stripe v-loading="loading">
        <el-table-column prop="name" :label="t('apiKey.name')" width="150" />
        <el-table-column prop="key" :label="t('apiKey.key')" width="280">
          <template #default="{ row }">
            <div class="flex items-center gap-2">
              <span class="text-gray-400 font-mono text-sm">{{ maskKey(row.key) }}</span>
              <el-button size="small" text @click="copyKey(row.key)">
                <el-icon><CopyDocument /></el-icon>
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" :label="t('apiKey.enabled')" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'danger'" size="small">
              {{ row.enabled ? t('common.yes') : t('common.no') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('apiKey.bindToAll')" width="110">
          <template #default="{ row }">
            <el-tag :type="(row.bind_to_all ?? row.bindToAllChannels) ? 'success' : 'info'" size="small">
              {{ (row.bind_to_all ?? row.bindToAllChannels) ? t('common.yes') : t('common.no') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Channels" min-width="180">
          <template #default="{ row }">
            <div v-if="row.bind_to_all ?? row.bindToAllChannels" class="flex items-center">
              <el-tag type="primary" size="small">All Channels</el-tag>
            </div>
            <div v-else-if="row.channels && row.channels.length > 0" class="flex flex-wrap gap-1">
              <el-tag
                v-for="c in row.channels.slice(0, 3)"
                :key="c.id"
                size="small"
                type="info"
                class="max-w-[100px] overflow-hidden"
              >
                <span class="truncate block">{{ c.name || c }}</span>
              </el-tag>
              <el-tag v-if="row.channels.length > 3" size="small" type="info">
                +{{ row.channels.length - 3 }}
              </el-tag>
            </div>
            <span v-else class="text-gray-400 text-sm">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('apiKey.logDetails')" width="110">
          <template #default="{ row }">
            <el-tag :type="(row.log_details ?? row.logDetails) ? 'success' : 'info'" size="small">
              {{ (row.log_details ?? row.logDetails) ? t('common.yes') : t('common.no') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('apiKey.lastUsed')" width="160">
          <template #default="{ row }">
            {{ (row.last_used || row.lastUsed) ? formatDate(row.last_used || row.lastUsed) : '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEditDialog(row)">{{ t('common.edit') }}</el-button>
            <el-button size="small" link :type="row.enabled ? 'warning' : 'success'" @click="toggleEnabled(row)">
              {{ row.enabled ? 'Disable' : 'Enable' }}
            </el-button>
            <el-button size="small" link type="danger" @click="deleteKey(row)">{{ t('common.delete') }}</el-button>
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
        />
      </div>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? t('apiKey.editTitle') : t('apiKey.createTitle')" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item :label="t('apiKey.name')" prop="name">
          <el-input v-model="form.name" placeholder="Enter a name for this API key" />
        </el-form-item>
        <el-form-item :label="t('apiKey.enabled')" prop="enabled" v-if="isEdit">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item :label="t('apiKey.bindToAll')" prop="bind_to_all">
          <div class="flex flex-col gap-1">
            <el-switch v-model="form.bind_to_all" />
            <span class="text-xs text-gray-500">Allow access to all channels</span>
          </div>
        </el-form-item>
        <el-form-item label="Channels" prop="channels" v-if="!form.bind_to_all">
          <el-select v-model="form.channels" multiple placeholder="Select Channels" class="w-full">
            <el-option v-for="c in channels" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('apiKey.logDetails')" prop="log_details">
          <div class="flex flex-col gap-1">
            <el-switch v-model="form.log_details" />
            <span class="text-xs text-gray-500">Log request and response details</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- New Key Display Dialog -->
    <el-dialog v-model="showKeyDialog" title="New API Key" width="500px">
      <el-alert type="warning" :closable="false" class="mb-4">
        Please save this key. It will not be shown again.
      </el-alert>
      <div class="flex items-center gap-2">
        <el-input :value="newKey" readonly class="font-mono" />
        <el-button type="primary" @click="copyKey(newKey)">Copy</el-button>
      </div>
      <template #footer>
        <el-button type="primary" @click="showKeyDialog = false">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- API Usage Examples -->
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <span class="text-lg font-semibold">API Usage Examples</span>
        </div>
      </template>
      <div class="space-y-6">
        <!-- Chat Completion -->
        <div>
          <h4 class="font-medium text-gray-800 mb-2">Chat Completion</h4>
          <p class="text-sm text-gray-500 mb-3">Send a chat completion request to the API gateway.</p>
          <div class="bg-gray-900 rounded-lg p-4 overflow-x-auto">
            <pre class="text-green-400 text-sm font-mono whitespace-pre-wrap">{{ curlExample }}</pre>
          </div>
        </div>
        <!-- Streaming -->
        <div>
          <h4 class="font-medium text-gray-800 mb-2">Streaming Chat Completion</h4>
          <p class="text-sm text-gray-500 mb-3">Enable streaming for real-time responses.</p>
          <div class="bg-gray-900 rounded-lg p-4 overflow-x-auto">
            <pre class="text-green-400 text-sm font-mono whitespace-pre-wrap">{{ curlStreamExample }}</pre>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'
import { apiKeyApi } from '@/api/apiKey'
import { channelApi } from '@/api/channel'
import type { GatewayAPIKey } from '@/types/apiKey'
import type { Channel } from '@/types/channel'
import dayjs from 'dayjs'

const { t } = useI18n()
const loading = ref(false)
const submitting = ref(false)
const apiKeys = ref<GatewayAPIKey[]>([])
const channels = ref<Channel[]>([])
const dialogVisible = ref(false)
const showKeyDialog = ref(false)
const newKey = ref('')
const isEdit = ref(false)
const selectedKey = ref<GatewayAPIKey | null>(null)
const formRef = ref<FormInstance>()

const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
})

const form = reactive({
  name: '',
  enabled: true,
  bind_to_all: true,
  log_details: false,
  channels: [] as number[]
})

const rules: FormRules = {
  name: [{ required: true, message: 'Name is required', trigger: 'blur' }]
}

// Frontend pagination slicing
const paginatedKeys = computed(() => {
  const start = (pagination.page - 1) * pagination.pageSize
  const end = start + pagination.pageSize
  return apiKeys.value.slice(start, end)
})

const formatDate = (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm')
const maskKey = (key: string) => key ? key.slice(0, 8) + '...' + key.slice(-4) : ''

const apiBaseUrl = typeof window !== 'undefined' ? window.location.origin : ''

const curlExample = computed(() => `curl -X POST ${apiBaseUrl}/api/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "Hello, world!"}]
  }'`)

const curlStreamExample = computed(() => `curl -X POST ${apiBaseUrl}/api/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "Tell me a story."}],
    "stream": true
  }'`)

const copyKey = async (key: string) => {
  try {
    await navigator.clipboard.writeText(key)
    ElMessage.success(t('apiKey.copyKey') + ' success')
  } catch {
    ElMessage.error('Copy failed')
  }
}

const fetchApiKeys = async () => {
  loading.value = true
  try {
    const response = await apiKeyApi.list()
    apiKeys.value = response.data || []
    pagination.total = apiKeys.value.length
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    loading.value = false
  }
}

const fetchChannels = async () => {
  try {
    const response = await channelApi.list()
    channels.value = response.data || []
  } catch (error) {
    console.error('Failed to fetch channels')
  }
}

const resetForm = () => {
  form.name = ''
  form.enabled = true
  form.bind_to_all = true
  form.log_details = false
  form.channels = []
}

const openCreateDialog = () => {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = (key: GatewayAPIKey) => {
  isEdit.value = true
  selectedKey.value = key
  form.name = key.name
  form.enabled = key.enabled
  form.bind_to_all = key.bind_to_all ?? key.bindToAllChannels ?? false
  form.log_details = key.log_details ?? key.logDetails ?? false
  form.channels = key.channels?.map(c => typeof c === 'object' ? c.id : c) || []
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
    if (isEdit.value && selectedKey.value) {
      await apiKeyApi.update(selectedKey.value.id, {
        name: form.name,
        enabled: form.enabled,
        bind_to_all: form.bind_to_all,
        log_details: form.log_details,
        channels: form.channels
      })
    } else {
      const response = await apiKeyApi.create({
        name: form.name,
        enabled: form.enabled,
        bind_to_all: form.bind_to_all,
        log_details: form.log_details,
        channels: form.channels
      })
      newKey.value = response.data.key
      showKeyDialog.value = true
    }
    ElMessage.success(t('common.success'))
    dialogVisible.value = false
    fetchApiKeys()
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    submitting.value = false
  }
}

const toggleEnabled = async (key: GatewayAPIKey) => {
  const action = key.enabled ? 'disable' : 'enable'
  try {
    await ElMessageBox.confirm(
      `Are you sure you want to ${action} this API key?`,
      t('common.confirm'),
      { type: 'warning' }
    )
    await apiKeyApi.update(key.id, {
      enabled: !key.enabled
    })
    ElMessage.success(t('common.success'))
    fetchApiKeys()
  } catch {
    // User cancelled
  }
}

const deleteKey = async (key: GatewayAPIKey) => {
  try {
    await ElMessageBox.confirm(t('common.confirmDelete'), t('common.confirm'), { type: 'warning' })
    await apiKeyApi.delete(key.id)
    ElMessage.success(t('common.success'))
    fetchApiKeys()
  } catch {
    // User cancelled
  }
}

onMounted(() => {
  fetchApiKeys()
  fetchChannels()
})
</script>