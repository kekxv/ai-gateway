<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('apiKey.title') }}</h2>
      <el-button type="primary" @click="openCreateDialog">
        {{ t('common.create') }}
      </el-button>
    </div>

    <!-- Card Grid -->
    <div v-if="loading" class="text-center py-12">
      <el-icon class="is-loading" :size="40"><Loading /></el-icon>
    </div>
    <div v-else-if="apiKeys.length === 0" class="text-center py-12 text-gray-500">
      {{ t('common.noData') }}
    </div>
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      <div
        v-for="key in paginatedKeys"
        :key="key.id"
        class="bg-white rounded-lg shadow-sm border border-gray-100 p-4 hover:shadow-md transition-shadow"
      >
        <!-- Header -->
        <div class="flex items-start justify-between mb-3 gap-2">
          <div class="flex-1 min-w-0">
            <h3 class="font-semibold text-gray-800 truncate">{{ key.name }}</h3>
            <div class="flex items-center gap-1 mt-1">
              <span class="text-sm text-gray-400 font-mono truncate">{{ maskKey(key.key) }}</span>
              <el-button size="small" text @click="copyKey(key.key)">
                <el-icon><CopyDocument /></el-icon>
              </el-button>
            </div>
          </div>
          <el-tag :type="key.enabled ? 'success' : 'danger'" size="small" class="shrink-0">
            {{ key.enabled ? t('common.enabled') : t('common.disabled') }}
          </el-tag>
        </div>

        <!-- Channels -->
        <div class="mb-3">
          <div class="text-xs text-gray-400 mb-1">{{ t('apiKey.channels') }}</div>
          <div v-if="key.bind_to_all ?? key.bindToAllChannels" class="flex items-center">
            <el-tag type="primary" size="small">All Channels</el-tag>
          </div>
          <div v-else-if="key.channels && key.channels.length > 0" class="flex flex-wrap gap-1">
            <el-tag
              v-for="c in key.channels.slice(0, 2)"
              :key="typeof c === 'object' ? c.id : c"
              size="small"
              type="info"
              effect="plain"
              class="max-w-[80px]"
            >
              <span class="truncate">{{ typeof c === 'object' ? c.name : c }}</span>
            </el-tag>
            <el-tag v-if="key.channels.length > 2" size="small" type="info" effect="plain">
              +{{ key.channels.length - 2 }}
            </el-tag>
          </div>
          <span v-else class="text-sm text-gray-400">-</span>
        </div>

        <!-- Stats -->
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div class="bg-gray-50 rounded-lg p-2 text-center">
            <div class="text-xs text-gray-500">{{ t('apiKey.logDetails') }}</div>
            <el-tag :type="(key.log_details ?? key.logDetails) ? 'success' : 'info'" size="small" class="mt-1">
              {{ (key.log_details ?? key.logDetails) ? t('common.yes') : t('common.no') }}
            </el-tag>
          </div>
          <div class="bg-gray-50 rounded-lg p-2 text-center">
            <div class="text-xs text-gray-500">{{ t('apiKey.lastUsed') }}</div>
            <div class="text-xs text-gray-600 mt-1 truncate">
              {{ (key.last_used || key.lastUsed) ? formatDate(String(key.last_used || key.lastUsed)) : '-' }}
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex flex-wrap gap-2 pt-3 border-t border-gray-100">
          <el-button size="small" @click="openEditDialog(key)">
            <el-icon class="mr-1"><Edit /></el-icon>
            {{ t('common.edit') }}
          </el-button>
          <el-button size="small" :type="key.enabled ? 'warning' : 'success'" @click="toggleEnabled(key)">
            {{ key.enabled ? 'Disable' : 'Enable' }}
          </el-button>
          <el-button size="small" type="danger" @click="deleteKey(key)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="apiKeys.length > 0" class="flex justify-center mt-6">
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
    <el-dialog v-model="dialogVisible" :title="isEdit ? t('apiKey.editTitle') : t('apiKey.createTitle')" :width="isMobile ? '90%' : '500px'">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" label-position="top">
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
    <el-dialog v-model="showKeyDialog" title="New API Key" :width="isMobile ? '90%' : '500px'">
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
      <!-- Provider Tabs -->
      <el-tabs v-model="activeProviderTab" class="mb-4">
        <el-tab-pane label="OpenAI" name="openai" />
        <el-tab-pane label="Anthropic" name="anthropic" />
      </el-tabs>

      <!-- OpenAI Examples -->
      <div v-show="activeProviderTab === 'openai'" class="space-y-6">
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

      <!-- Anthropic Examples -->
      <div v-show="activeProviderTab === 'anthropic'" class="space-y-6">
        <!-- Messages API -->
        <div>
          <h4 class="font-medium text-gray-800 mb-2">Messages API</h4>
          <p class="text-sm text-gray-500 mb-3">Send a messages request using Anthropic API format.</p>
          <div class="bg-gray-900 rounded-lg p-4 overflow-x-auto">
            <pre class="text-green-400 text-sm font-mono whitespace-pre-wrap">{{ anthropicExample }}</pre>
          </div>
        </div>
        <!-- Streaming -->
        <div>
          <h4 class="font-medium text-gray-800 mb-2">Streaming Messages</h4>
          <p class="text-sm text-gray-500 mb-3">Enable streaming for real-time responses.</p>
          <div class="bg-gray-900 rounded-lg p-4 overflow-x-auto">
            <pre class="text-green-400 text-sm font-mono whitespace-pre-wrap">{{ anthropicStreamExample }}</pre>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from '@/plugins/element-plus-services'
import { CopyDocument, Loading, Edit, Delete } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
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
const isMobile = ref(false)
const activeProviderTab = ref('openai')

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  fetchApiKeys()
  fetchChannels()
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

const pagination = reactive({
  page: 1,
  pageSize: 12,
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

const anthropicExample = computed(() => `curl -X POST ${apiBaseUrl}/api/anthropic/v1/messages \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: YOUR_API_KEY" \\
  -H "anthropic-version: 2023-06-01" \\
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello, Claude!"}]
  }'`)

const anthropicStreamExample = computed(() => `curl -X POST ${apiBaseUrl}/api/anthropic/v1/messages \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: YOUR_API_KEY" \\
  -H "anthropic-version: 2023-06-01" \\
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 1024,
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
</script>
