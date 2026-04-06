<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('log.title') }}</h2>
      <el-button type="danger" plain size="small" @click="cleanupLogs">
        <el-icon class="mr-1"><Delete /></el-icon>
        清理旧日志
      </el-button>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-2 items-center text-sm">
      <el-input v-model="filters.model" placeholder="模型" clearable class="!w-32 sm:!w-48" size="small" />
      <el-input v-model="filters.provider" placeholder="提供商" clearable class="!w-28 sm:!w-36" size="small" />
      <el-select v-model="filters.status" placeholder="状态" clearable class="!w-20 sm:!w-24" size="small">
        <el-option label="成功" value="success" />
        <el-option label="错误" value="error" />
      </el-select>
      <el-date-picker
        v-model="filters.dateRange"
        type="daterange"
        range-separator="-"
        start-placeholder="开始"
        end-placeholder="结束"
        class="!w-48 sm:!w-52"
        size="small"
      />
      <el-button type="primary" size="small" @click="fetchLogs">搜索</el-button>
      <el-button size="small" @click="resetFilters">重置</el-button>
    </div>

    <!-- Desktop Table -->
    <el-card shadow="never" class="border-0 hidden lg:block">
      <el-table :data="logs" v-loading="loading" class="w-full">
        <el-table-column :label="t('log.timestamp')" width="170">
          <template #default="{ row }">
            <span class="text-sm text-gray-600 whitespace-nowrap">{{ formatDate(row.createdAt) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('log.apiKey')" width="120">
          <template #default="{ row }">
            <span v-if="row.apiKey" class="text-sm">{{ row.apiKey.name }}</span>
            <span v-else class="text-gray-300">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('log.userAccount')" width="140">
          <template #default="{ row }">
            <span v-if="row.apiKey?.user" class="text-sm text-gray-600 truncate block">{{ row.apiKey.user.email }}</span>
            <span v-else class="text-gray-300">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('log.model')" min-width="140">
          <template #default="{ row }">
            <el-tag type="info" size="small" class="font-mono">{{ row.modelName || row.model || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('log.provider')" width="110">
          <template #default="{ row }">
            <span class="text-sm whitespace-nowrap">{{ row.providerName || row.provider || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('log.latency')" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="getLatencyType(row.latency || row.latency_ms)" size="small">
              {{ formatLatency(row.latency || row.latency_ms) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('log.promptTokens')" width="90" align="right">
          <template #default="{ row }">
            <span class="text-indigo-600 font-medium text-sm whitespace-nowrap">{{ formatNumber(row.promptTokens || row.prompt_tokens) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('log.completionTokens')" width="110" align="right">
          <template #default="{ row }">
            <span class="text-green-600 font-medium text-sm whitespace-nowrap">{{ formatNumber(row.completionTokens || row.completion_tokens) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('log.totalTokens')" width="110" align="right">
          <template #default="{ row }">
            <span class="font-semibold text-sm whitespace-nowrap">{{ formatNumber(row.totalTokens || row.total_tokens) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('log.cost')" width="85" align="right">
          <template #default="{ row }">
            <span class="text-amber-600 text-sm whitespace-nowrap">{{ formatCost(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('log.status')" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ row.status === 200 || row.status === 'success' ? '成功' : '错误' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('log.detail')" width="70" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" class="!px-2 !py-1 hover:!bg-indigo-50 rounded" @click="viewDetail(row)">
              <el-icon class="mr-1"><View /></el-icon>详情
            </el-button>
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
          @change="fetchLogs"
        />
      </div>
    </el-card>

    <!-- Mobile Card List -->
    <div class="lg:hidden space-y-3">
      <div v-if="loading" class="text-center py-8">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      </div>
      <div
        v-for="log in logs"
        :key="log.id"
        class="bg-white rounded-lg shadow-sm border border-gray-100 p-3"
      >
        <div class="flex items-start justify-between mb-2">
          <div class="flex-1 min-w-0">
            <el-tag type="info" size="small" class="font-mono mb-1">{{ log.modelName || log.model || '-' }}</el-tag>
            <div class="text-xs text-gray-400">{{ formatDate(log.createdAt) }}</div>
          </div>
          <el-tag :type="getStatusType(log.status)" size="small">
            {{ log.status === 200 || log.status === 'success' ? '成功' : '错误' }}
          </el-tag>
        </div>
        <div class="grid grid-cols-3 gap-2 text-center mb-2">
          <div class="bg-indigo-50 rounded p-1.5">
            <div class="text-xs text-indigo-500">输入</div>
            <div class="text-sm font-semibold text-indigo-700">{{ formatNumber(log.promptTokens || log.prompt_tokens) }}</div>
          </div>
          <div class="bg-green-50 rounded p-1.5">
            <div class="text-xs text-green-500">输出</div>
            <div class="text-sm font-semibold text-green-700">{{ formatNumber(log.completionTokens || log.completion_tokens) }}</div>
          </div>
          <div class="bg-amber-50 rounded p-1.5">
            <div class="text-xs text-amber-500">费用</div>
            <div class="text-sm font-semibold text-amber-700">{{ formatCost(log.cost) }}</div>
          </div>
        </div>
        <div class="flex items-center justify-between text-xs text-gray-500">
          <span>{{ log.providerName || log.provider || '-' }}</span>
          <el-tag :type="getLatencyType(log.latency || log.latency_ms)" size="small">
            {{ formatLatency(log.latency || log.latency_ms) }}
          </el-tag>
        </div>
        <div class="flex justify-end pt-2 mt-2 border-t border-gray-100">
          <el-button size="small" link type="primary" @click="viewDetail(log)">
            <el-icon class="mr-1"><View /></el-icon>详情
          </el-button>
        </div>
      </div>
      <!-- Mobile Pagination -->
      <div class="flex justify-center mt-4">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="prev, pager, next"
          size="small"
          @change="fetchLogs"
        />
      </div>
    </div>

    <!-- Detail Dialog -->
    <el-dialog v-model="detailDialogVisible" title="日志详情" :width="isMobile ? '95%' : '800px'" destroy-on-close>
      <div v-if="logDetail" class="space-y-4">
        <!-- Stats Grid -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="stat-card stat-card-indigo">
            <div class="stat-label">{{ t('log.promptTokens') }}</div>
            <div class="stat-value">{{ formatNumber(logDetail.promptTokens || logDetail.prompt_tokens) }}</div>
          </div>
          <div class="stat-card stat-card-green">
            <div class="stat-label">{{ t('log.completionTokens') }}</div>
            <div class="stat-value">{{ formatNumber(logDetail.completionTokens || logDetail.completion_tokens) }}</div>
          </div>
          <div class="stat-card stat-card-purple">
            <div class="stat-label">{{ t('log.totalTokens') }}</div>
            <div class="stat-value">{{ formatNumber(logDetail.totalTokens || logDetail.total_tokens) }}</div>
          </div>
          <div class="stat-card stat-card-amber">
            <div class="stat-label">{{ t('log.cost') }}</div>
            <div class="stat-value">{{ formatCost(logDetail.cost) }}</div>
          </div>
        </div>

        <!-- Info Grid -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div class="info-card">
            <div class="info-label">{{ t('log.timestamp') }}</div>
            <div class="info-value text-xs">{{ formatDate(logDetail.createdAt) }}</div>
          </div>
          <div class="info-card">
            <div class="info-label">{{ t('log.apiKey') }}</div>
            <div class="info-value truncate">{{ logDetail.apiKey?.name || '-' }}</div>
          </div>
          <div class="info-card">
            <div class="info-label">{{ t('log.model') }}</div>
            <div class="info-value truncate">{{ logDetail.modelName || logDetail.model || '-' }}</div>
          </div>
          <div class="info-card">
            <div class="info-label">{{ t('log.latency') }}</div>
            <div class="info-value">{{ formatLatency(logDetail.latency || logDetail.latency_ms) }}</div>
          </div>
        </div>

        <!-- Request Headers -->
        <div v-if="parsedRequestHeaders && Object.keys(parsedRequestHeaders).length > 0" class="headers-card">
          <div class="headers-header">
            <el-icon class="text-blue-500"><Document /></el-icon>
            <span class="font-medium">请求头</span>
          </div>
          <div class="headers-body">
            <div v-for="(value, key) in parsedRequestHeaders" :key="key" class="headers-row">
              <span class="headers-key">{{ key }}</span>
              <span class="headers-value">{{ value }}</span>
            </div>
          </div>
        </div>

        <!-- Response Headers -->
        <div v-if="parsedResponseHeaders && Object.keys(parsedResponseHeaders).length > 0" class="headers-card headers-card-green">
          <div class="headers-header">
            <el-icon class="text-green-500"><Document /></el-icon>
            <span class="font-medium">响应头</span>
          </div>
          <div class="headers-body">
            <div v-for="(value, key) in parsedResponseHeaders" :key="key" class="headers-row">
              <span class="headers-key">{{ key }}</span>
              <span class="headers-value">{{ value }}</span>
            </div>
          </div>
        </div>

        <!-- Error Message (show if exists) -->
        <div v-if="logDetail.errorMessage || logDetail.error_message" class="error-card">
          <div class="flex items-start gap-3">
            <el-icon class="text-red-500 text-xl mt-0.5"><Warning /></el-icon>
            <div>
              <div class="text-red-600 font-semibold mb-1">错误信息</div>
              <div class="text-red-600/90 text-sm whitespace-pre-wrap break-words">{{ logDetail.errorMessage || logDetail.error_message }}</div>
            </div>
          </div>
        </div>

        <!-- Chat Messages (show when available) -->
        <div v-if="chatMessages.length > 0" class="chat-container">
          <div class="chat-header">
            <span class="font-medium">对话内容</span>
            <span class="chat-count">{{ chatMessages.length }} 条消息</span>
          </div>
          <div class="chat-body">
            <div
              v-for="(msg, idx) in chatMessages"
              :key="idx"
              class="chat-message-wrapper"
            >
              <!-- User message - right side -->
              <div v-if="msg.role === 'user'" class="chat-float-right">
                <div class="chat-row-reverse">
                  <div class="chat-avatar-indigo">U</div>
                  <div class="chat-bubble-wrapper">
                    <div class="chat-bubble-user-bg">
                      <div class="chat-role-label-right">User</div>
                      <div class="chat-content-left">{{ msg.content }}</div>
                    </div>
                  </div>
                </div>
              </div>
              <!-- Assistant message - left side -->
              <div v-else-if="msg.role === 'assistant'" class="chat-float-left">
                <div class="chat-row">
                  <div class="chat-avatar-green">A</div>
                  <div class="chat-bubble-wrapper">
                    <div class="chat-bubble-assistant-bg">
                      <div class="chat-role-label-left">Assistant</div>
                      <div class="chat-content">{{ msg.content }}</div>
                    </div>
                  </div>
                </div>
              </div>
              <!-- System message - center -->
              <div v-else-if="msg.role === 'system'" class="chat-float-center">
                <div class="chat-bubble-system-bg">
                  <div class="chat-role-label-center">System</div>
                  <div class="chat-content">{{ msg.content }}</div>
                </div>
              </div>
              <!-- Tool message - center -->
              <div v-else class="chat-float-center">
                <div class="chat-bubble-tool-bg">
                  <div class="chat-role-label-center">Tool</div>
                  <div class="chat-content">{{ msg.content }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Raw Request/Response (show only when has content) -->
        <template v-else>
          <div v-if="logDetail.detail?.requestBody" class="raw-card">
            <div class="raw-header">
              <span>{{ t('log.request') }}</span>
              <el-button size="small" text @click="copyToClipboard(logDetail.detail.requestBody)">
                <el-icon><CopyDocument /></el-icon>
              </el-button>
            </div>
            <pre class="raw-body">{{ formatJson(logDetail.detail.requestBody) }}</pre>
          </div>
          <div v-if="logDetail.detail?.responseBody" class="raw-card">
            <div class="raw-header">
              <span>{{ t('log.response') }}</span>
              <el-button size="small" text @click="copyToClipboard(logDetail.detail.responseBody)">
                <el-icon><CopyDocument /></el-icon>
              </el-button>
            </div>
            <pre class="raw-body">{{ formatJson(logDetail.detail.responseBody) }}</pre>
          </div>
        </template>
      </div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, View, CopyDocument, Warning, Loading, Document } from '@element-plus/icons-vue'
import { logApi } from '@/api/log'
import type { Log, LogDetail } from '@/types/log'
import dayjs from 'dayjs'

const { t } = useI18n()
const loading = ref(false)
const logs = ref<Log[]>([])
const logDetail = ref<LogDetail | null>(null)
const detailDialogVisible = ref(false)
const isMobile = ref(false)

// Parse headers JSON
const parsedRequestHeaders = computed(() => {
  if (!logDetail.value?.requestHeaders) return null
  try {
    return JSON.parse(logDetail.value.requestHeaders)
  } catch {
    return null
  }
})

const parsedResponseHeaders = computed(() => {
  if (!logDetail.value?.responseHeaders) return null
  try {
    return JSON.parse(logDetail.value.responseHeaders)
  } catch {
    return null
  }
})

const checkMobile = () => {
  isMobile.value = window.innerWidth < 1024
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  fetchLogs()
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
})

const filters = reactive({
  model: '',
  provider: '',
  status: '',
  dateRange: null as [Date, Date] | null
})

const formatDate = (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm:ss')
const formatNumber = (num: number | undefined) => (num || 0).toLocaleString()
const formatCost = (cost: number | undefined) => '$' + ((cost || 0) / 10000).toFixed(4)

const formatLatency = (ms: number | undefined) => {
  const value = ms || 0
  if (value < 1000) return `${value}ms`
  if (value < 60000) return `${(value / 1000).toFixed(1)}s`
  if (value < 3600000) return `${(value / 60000).toFixed(1)}m`
  return `${(value / 3600000).toFixed(1)}h`
}

const getLatencyType = (latency: number | undefined) => {
  const ms = latency || 0
  if (ms < 1000) return 'success'
  if (ms < 3000) return 'warning'
  return 'danger'
}

const getStatusType = (status: number | string) => {
  if (status === 200 || status === 'success') return 'success'
  return 'danger'
}

const formatJson = (json: string | object | null | undefined) => {
  if (!json) return 'N/A'
  try {
    const obj = typeof json === 'string' ? JSON.parse(json) : json
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(json)
  }
}

const copyToClipboard = async (text: string | object | null | undefined) => {
  if (!text) return
  try {
    await navigator.clipboard.writeText(typeof text === 'string' ? text : JSON.stringify(text, null, 2))
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

// Extract chat messages from request/response
const chatMessages = computed(() => {
  if (!logDetail.value?.detail) return []
  const messages: { role: string; content: string }[] = []

  // Extract from request body
  try {
    const request = logDetail.value.detail.requestBody
    if (request) {
      const reqObj = typeof request === 'string' ? JSON.parse(request) : request

      // Handle Responses API format (input field)
      if (reqObj.input) {
        // Add instructions as system message if present
        if (reqObj.instructions) {
          messages.push({
            role: 'system',
            content: reqObj.instructions
          })
        }

        // Handle input - can be string or array
        if (typeof reqObj.input === 'string') {
          messages.push({
            role: 'user',
            content: reqObj.input
          })
        } else if (Array.isArray(reqObj.input)) {
          // Input is array of items
          reqObj.input.forEach((item: { type?: string; role?: string; content?: string | object }) => {
            if (item.type === 'message' || item.role) {
              let content = ''
              if (typeof item.content === 'string') {
                content = item.content
              } else if (item.content && typeof item.content === 'object') {
                // Content might be { StringContent, Parts } or array
                const contentObj = item.content as { StringContent?: string; Parts?: { text?: string }[] }
                if (contentObj.StringContent) {
                  content = contentObj.StringContent
                } else if (Array.isArray(item.content)) {
                  content = item.content.map((p: { text?: string; type?: string }) => p.text || '').join('')
                } else {
                  content = JSON.stringify(item.content, null, 2)
                }
              }
              messages.push({
                role: item.role || 'user',
                content
              })
            }
          })
        }
      }
      // Handle Chat Completions API format (messages field)
      else if (reqObj.messages && Array.isArray(reqObj.messages)) {
        reqObj.messages.forEach((msg: { role: string; content: string | object }) => {
          messages.push({
            role: msg.role,
            content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content, null, 2)
          })
        })
      }
    }
  } catch {
    // Ignore parse errors
  }

  // Extract from response body (assistant reply)
  try {
    const response = logDetail.value.detail.responseBody
    if (response) {
      const respObj = typeof response === 'string' ? JSON.parse(response) : response

      // Handle Responses API format (output field)
      if (respObj.output && Array.isArray(respObj.output)) {
        respObj.output.forEach((item: { type?: string; role?: string; content?: object[]; output_text?: string }) => {
          if (item.type === 'message' && item.content) {
            // Extract text from content array
            const text = item.content
              .filter((c: { type?: string; text?: string }) => c.type === 'output_text' && c.text)
              .map((c: { text?: string }) => c.text)
              .join('')
            if (text) {
              messages.push({
                role: item.role || 'assistant',
                content: text
              })
            }
          }
        })
        // Also check output_text at top level
        if (respObj.output_text && messages.filter(m => m.role === 'assistant').length === 0) {
          messages.push({
            role: 'assistant',
            content: respObj.output_text
          })
        }
      }
      // Handle Chat Completions API format (choices field)
      else if (respObj.choices && Array.isArray(respObj.choices)) {
        respObj.choices.forEach((choice: { message?: { role: string; content: string | object } }) => {
          if (choice.message) {
            messages.push({
              role: choice.message.role,
              content: typeof choice.message.content === 'string' ? choice.message.content : JSON.stringify(choice.message.content, null, 2)
            })
          }
        })
      }
    }
  } catch {
    // Ignore parse errors
  }

  return messages
})

const fetchLogs = async () => {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: pagination.page,
      page_size: pagination.pageSize
    }
    if (filters.model) params.model = filters.model
    if (filters.provider) params.provider = filters.provider
    if (filters.status) params.status = filters.status
    if (filters.dateRange) {
      params.start_date = dayjs(filters.dateRange[0]).format('YYYY-MM-DD')
      params.end_date = dayjs(filters.dateRange[1]).format('YYYY-MM-DD')
    }

    const response = await logApi.list(params)
    logs.value = response.data.logs || response.data
    pagination.total = response.data.total || logs.value.length
  } catch (error) {
    ElMessage.error(t('common.error'))
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.model = ''
  filters.provider = ''
  filters.status = ''
  filters.dateRange = null
  pagination.page = 1
  fetchLogs()
}

const viewDetail = async (log: Log) => {
  try {
    const response = await logApi.getDetail(log.id)
    // Backend returns { log, detail: { requestBody, responseBody } }
    const data = response.data
    logDetail.value = {
      ...data.log,
      detail: data.detail || undefined
    }
    detailDialogVisible.value = true
  } catch (error) {
    ElMessage.error(t('common.error'))
  }
}

const cleanupLogs = async () => {
  try {
    await ElMessageBox.confirm('确定要清理 30 天前的日志吗？', '清理日志', { type: 'warning' })
    await logApi.cleanup(30)
    ElMessage.success('清理完成')
    fetchLogs()
  } catch {
    // User cancelled
  }
}
</script>

<style>
/* Stats cards */
.stat-card {
  border-radius: 12px;
  padding: 16px;
  text-align: center;
  transition: transform 0.2s, box-shadow 0.2s;
}
.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
.stat-card-indigo { background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%); }
.stat-card-green { background: linear-gradient(135deg, #ecfdf5 0%, #dcfce7 100%); }
.stat-card-purple { background: linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%); }
.stat-card-amber { background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); }
.stat-label {
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 4px;
}
.stat-card-indigo .stat-label { color: #6366f1; }
.stat-card-green .stat-label { color: #22c55e; }
.stat-card-purple .stat-label { color: #a855f7; }
.stat-card-amber .stat-label { color: #f59e0b; }
.stat-value {
  font-size: 24px;
  font-weight: 700;
}
.stat-card-indigo .stat-value { color: #4338ca; }
.stat-card-green .stat-value { color: #16a34a; }
.stat-card-purple .stat-value { color: #9333ea; }
.stat-card-amber .stat-value { color: #d97706; }

/* Info cards */
.info-card {
  background: #f9fafb;
  border-radius: 8px;
  padding: 12px;
}
.info-label {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 4px;
}
.info-value {
  font-weight: 500;
  color: #374151;
}

/* Headers card */
.headers-card {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  overflow: hidden;
}
.headers-card.headers-card-green {
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
  border-color: #bbf7d0;
}
.headers-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #bfdbfe;
  font-size: 14px;
}
.headers-card.headers-card-green .headers-header {
  border-color: #bbf7d0;
}
.headers-body {
  padding: 12px 16px;
  max-height: 200px;
  overflow-y: auto;
}
.headers-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px dashed #e5e7eb;
}
.headers-row:last-child {
  border-bottom: none;
}
.headers-key {
  font-size: 12px;
  font-weight: 500;
  color: #6366f1;
  min-width: 140px;
  flex-shrink: 0;
}
.headers-card.headers-card-green .headers-key {
  color: #22c55e;
}
.headers-value {
  font-size: 12px;
  color: #374151;
  word-break: break-all;
}

/* Error card */
.error-card {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border: 1px solid #fecaca;
  border-radius: 12px;
  padding: 16px;
}

/* Chat container */
.chat-container {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  overflow: hidden;
}
.chat-header {
  background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
  padding: 12px 16px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.chat-count {
  font-size: 12px;
  color: #9ca3af;
}
.chat-body {
  max-height: 320px;
  overflow-y: auto;
  padding: 16px;
  background: #fafafa;
}

/* Chat message styles - WeChat-like style */
.chat-message-wrapper {
  margin-bottom: 16px;
}
.chat-message-wrapper::after {
  content: '';
  display: block;
  clear: both;
}

/* Float layouts */
.chat-float-right {
  float: right;
  max-width: 85%;
}
.chat-float-left {
  float: left;
  max-width: 85%;
}
.chat-float-center {
  max-width: 85%;
  margin: 0 auto;
  clear: both;
}

/* Row layouts */
.chat-row-reverse {
  display: flex;
  flex-direction: row-reverse;
  align-items: flex-start;
}
.chat-row {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
}

/* Avatars */
.chat-avatar-indigo {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  color: white;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 12px;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}
.chat-avatar-green {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  color: white;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-right: 12px;
  box-shadow: 0 2px 8px rgba(34, 197, 94, 0.3);
}

/* Bubble wrapper */
.chat-bubble-wrapper {
  min-width: 0;
  flex: 1;
}

/* Bubble backgrounds with special corner (like WeChat tail) */
.chat-bubble-user-bg {
  background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
  border-radius: 16px;
  border-top-right-radius: 4px;
  padding: 12px 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
.chat-bubble-assistant-bg {
  background: linear-gradient(135deg, #ecfdf5 0%, #dcfce7 100%);
  border-radius: 16px;
  border-top-left-radius: 4px;
  padding: 12px 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
.chat-bubble-system-bg {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border-left: 3px solid #f59e0b;
  border-radius: 8px;
  padding: 12px 16px;
}
.chat-bubble-tool-bg {
  background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
  border-radius: 8px;
  padding: 12px 16px;
}

/* Role labels */
.chat-role-label-right {
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 4px;
  text-align: right;
  color: #6366f1;
}
.chat-role-label-left {
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 4px;
  text-align: left;
  color: #22c55e;
}
.chat-role-label-center {
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 4px;
  text-align: left;
  color: #6b7280;
}

/* Content */
.chat-content {
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
  color: #374151;
}
.chat-content-left {
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
  text-align: left;
  color: #374151;
}

/* Raw card */
.raw-card {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 12px;
}
.raw-header {
  background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
  padding: 10px 16px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 500;
  color: #374151;
}
.raw-body {
  background: #fafafa;
  padding: 16px;
  font-size: 12px;
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', monospace;
  color: #4b5563;
  overflow: auto;
  max-height: 200px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>