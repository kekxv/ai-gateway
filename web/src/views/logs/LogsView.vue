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
      <el-input v-model="filters.model" placeholder="模型" clearable class="!w-32 sm:!w-40" size="small" />
      <el-input v-model="filters.provider" placeholder="提供商" clearable class="!w-24 sm:!w-32" size="small" />
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
        class="!w-44 sm:!w-48"
        size="small"
      />
      <el-button type="primary" size="small" @click="fetchLogs">搜索</el-button>
      <el-button size="small" @click="resetFilters">重置</el-button>
    </div>

    <!-- Card Grid -->
    <div v-if="loading" class="text-center py-12">
      <el-icon class="is-loading" :size="40"><Loading /></el-icon>
    </div>
    <div v-else-if="logs.length === 0" class="text-center py-12 text-gray-500">
      {{ t('common.noData') }}
    </div>
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      <div
        v-for="log in logs"
        :key="log.id"
        class="bg-white rounded-lg shadow-sm border border-gray-100 p-3 hover:shadow-md transition-shadow cursor-pointer"
        @click="viewDetail(log)"
      >
        <!-- Header -->
        <div class="flex items-start justify-between mb-2 gap-2">
          <div class="flex-1 min-w-0">
            <el-tag type="info" size="small" class="font-mono">{{ log.modelName || log.model || '-' }}</el-tag>
          </div>
          <el-tag :type="getStatusType(log.status)" size="small" class="shrink-0">
            {{ log.status === 200 || log.status === 'success' ? '成功' : '错误' }}
          </el-tag>
        </div>

        <!-- Time & Provider -->
        <div class="flex items-center justify-between text-xs text-gray-400 mb-3">
          <span>{{ formatDate(log.createdAt) }}</span>
          <span>{{ log.providerName || log.provider || '-' }}</span>
        </div>

        <!-- Stats Grid -->
        <div class="grid grid-cols-3 gap-2 mb-2">
          <div class="bg-indigo-50 rounded p-1.5 text-center">
            <div class="text-xs text-indigo-500">输入</div>
            <div class="text-sm font-semibold text-indigo-700">{{ formatNumber(log.promptTokens || log.prompt_tokens) }}</div>
          </div>
          <div class="bg-green-50 rounded p-1.5 text-center">
            <div class="text-xs text-green-500">输出</div>
            <div class="text-sm font-semibold text-green-700">{{ formatNumber(log.completionTokens || log.completion_tokens) }}</div>
          </div>
          <div class="bg-amber-50 rounded p-1.5 text-center">
            <div class="text-xs text-amber-500">费用</div>
            <div class="text-sm font-semibold text-amber-700">{{ formatCost(log.cost) }}</div>
          </div>
        </div>

        <!-- Latency -->
        <div class="flex items-center justify-between text-xs">
          <span class="text-gray-400">
            {{ log.apiKey?.name ? log.apiKey.name : '-' }}
          </span>
          <el-tag :type="getLatencyType(log.latency || log.latency_ms)" size="small">
            {{ formatLatency(log.latency || log.latency_ms) }}
          </el-tag>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="logs.length > 0" class="flex justify-center mt-6">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[12, 24, 48, 96]"
        layout="total, sizes, prev, pager, next"
        :size="isMobile ? 'small' : 'default'"
        @change="fetchLogs"
      />
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

        <!-- View Mode Toggle -->
        <div class="flex gap-2">
          <el-button
            :type="viewMode === 'chat' ? 'primary' : 'default'"
            size="small"
            @click="viewMode = 'chat'"
          >
            <el-icon class="mr-1"><ChatDotRound /></el-icon>
            对话模式
          </el-button>
          <el-button
            :type="viewMode === 'meta' ? 'primary' : 'default'"
            size="small"
            @click="viewMode = 'meta'"
          >
            <el-icon class="mr-1"><DataLine /></el-icon>
            元数据模式
          </el-button>
        </div>

        <!-- Request Headers (Collapsible) - always show -->
        <div v-if="parsedRequestHeaders && Object.keys(parsedRequestHeaders).length > 0" class="headers-card">
          <div class="headers-header cursor-pointer select-none" @click="requestHeadersCollapsed = !requestHeadersCollapsed">
            <div class="flex items-center gap-2">
              <el-icon class="text-blue-500"><Document /></el-icon>
              <span class="font-medium">请求头</span>
              <span class="text-xs text-gray-400">({{ Object.keys(parsedRequestHeaders).length }} 项)</span>
            </div>
            <el-icon :class="{ 'rotate-180': !requestHeadersCollapsed }" class="transition-transform"><ArrowDown /></el-icon>
          </div>
          <div v-show="!requestHeadersCollapsed" class="headers-body">
            <div v-for="(value, key) in parsedRequestHeaders" :key="key" class="headers-row">
              <span class="headers-key">{{ key }}</span>
              <span class="headers-value">{{ value }}</span>
            </div>
          </div>
        </div>

        <!-- Response Headers (Collapsible) - always show -->
        <div v-if="parsedResponseHeaders && Object.keys(parsedResponseHeaders).length > 0" class="headers-card headers-card-green">
          <div class="headers-header cursor-pointer select-none" @click="responseHeadersCollapsed = !responseHeadersCollapsed">
            <div class="flex items-center gap-2">
              <el-icon class="text-green-500"><Document /></el-icon>
              <span class="font-medium">响应头</span>
              <span class="text-xs text-gray-400">({{ Object.keys(parsedResponseHeaders).length }} 项)</span>
            </div>
            <el-icon :class="{ 'rotate-180': !responseHeadersCollapsed }" class="transition-transform"><ArrowDown /></el-icon>
          </div>
          <div v-show="!responseHeadersCollapsed" class="headers-body">
            <div v-for="(value, key) in parsedResponseHeaders" :key="key" class="headers-row">
              <span class="headers-key">{{ key }}</span>
              <span class="headers-value">{{ value }}</span>
            </div>
          </div>
        </div>

        <!-- Error Message (show if exists) - always show -->
        <div v-if="logDetail.errorMessage || logDetail.error_message" class="error-card">
          <div class="flex items-start gap-3">
            <el-icon class="text-red-500 text-xl mt-0.5"><Warning /></el-icon>
            <div>
              <div class="text-red-600 font-semibold mb-1">错误信息</div>
              <div class="text-red-600/90 text-sm whitespace-pre-wrap break-words">{{ logDetail.errorMessage || logDetail.error_message }}</div>
            </div>
          </div>
        </div>

        <!-- Chat Mode - request/response body as chat messages -->
        <template v-if="viewMode === 'chat'">

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
              class="message-block"
              :class="msg.role"
            >
              <!-- System message - right side like user -->
              <div v-if="msg.role === 'system'" class="system-message">
                <div class="system-bubble">
                  <div class="system-label-text">System</div>
                  <div class="system-content">{{ msg.content }}</div>
                </div>
              </div>
              <!-- User Message -->
              <div v-else-if="msg.role === 'user'" class="user-message">
                <div class="user-bubble">{{ msg.content }}</div>
              </div>
              <!-- Assistant Message -->
              <div v-else-if="msg.role === 'assistant'" class="assistant-message">
                <div class="assistant-avatar">
                  <el-icon><Monitor /></el-icon>
                </div>
                <div class="assistant-content">
                  <div class="assistant-name">AI</div>
                  <!-- Think Block -->
                  <ThinkBlock
                    v-if="msg.hasThink && msg.thinkContent"
                    :content="msg.thinkContent"
                    :tokens="estimateThinkTokens(msg.thinkContent)"
                    :default-collapsed="true"
                    :force-expand="!msg.content && (!msg.toolCalls || msg.toolCalls.length === 0)"
                  />
                  <!-- Tool Calls Display -->
                  <ToolCallDisplay
                    v-if="msg.toolCalls && msg.toolCalls.length > 0"
                    :tool-calls="msg.toolCalls"
                  />
                  <!-- Content -->
                  <div v-if="msg.content" class="assistant-bubble">
                    <MarkdownRenderer :content="msg.content" />
                  </div>
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
        </template>

        <!-- Meta Mode - request/response body with syntax highlighting -->
        <template v-else-if="viewMode === 'meta'">
          <!-- Request Body (highlighted) -->
          <div v-if="logDetail.detail?.requestBody" class="meta-card">
            <div class="meta-header">
              <span class="font-medium">请求体</span>
              <el-button size="small" text @click="copyToClipboard(logDetail.detail.requestBody)">
                <el-icon><CopyDocument /></el-icon>
              </el-button>
            </div>
            <pre class="meta-body" v-html="highlightJson(logDetail.detail.requestBody)"></pre>
          </div>

          <!-- Response Body (highlighted) -->
          <div v-if="logDetail.detail?.responseBody" class="meta-card">
            <div class="meta-header">
              <span class="font-medium">响应体</span>
              <el-button size="small" text @click="copyToClipboard(logDetail.detail.responseBody)">
                <el-icon><CopyDocument /></el-icon>
              </el-button>
            </div>
            <pre class="meta-body" v-html="highlightJson(logDetail.detail.responseBody)"></pre>
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
import { Delete, CopyDocument, Warning, Loading, Monitor, Document, ChatDotRound, DataLine, ArrowDown } from '@element-plus/icons-vue'
import { logApi } from '@/api/log'
import type { Log, LogDetail } from '@/types/log'
import type { ToolCallResult } from '@/types/tool'
import { parseMessageContent, estimateThinkTokens } from '@/utils/messageParser'
import ThinkBlock from '@/components/chat/ThinkBlock.vue'
import ToolCallDisplay from '@/components/chat/ToolCallDisplay.vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import dayjs from 'dayjs'
import 'highlight.js/styles/github.css'
import hljs from 'highlight.js'

const { t } = useI18n()
const loading = ref(false)
const logs = ref<Log[]>([])
const logDetail = ref<LogDetail | null>(null)
const detailDialogVisible = ref(false)
const isMobile = ref(false)

// 显示模式：'chat' 对话模式, 'meta' 元数据模式
const viewMode = ref<'chat' | 'meta'>('chat')

// 折叠状态
const requestHeadersCollapsed = ref(true)
const responseHeadersCollapsed = ref(true)

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

// 语法高亮 JSON
const highlightJson = (json: string | object | null | undefined): string => {
  if (!json) return ''
  try {
    const obj = typeof json === 'string' ? JSON.parse(json) : json
    const formatted = JSON.stringify(obj, null, 2)
    return hljs.highlight(formatted, { language: 'json' }).value
  } catch {
    return String(json)
  }
}

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
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
  pageSize: 12,
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

// Helper function to extract text from content
const extractContentText = (content: string | object | undefined): string => {
  if (!content) return ''
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    // Handle [{type: "text", text: "..."}] format
    return content
      .map((item: { type?: string; text?: string }) => {
        if (item.type === 'text' && item.text) return item.text
        return ''
      })
      .join('')
  }
  if (typeof content === 'object') {
    // Handle { StringContent, Parts } or similar
    const contentObj = content as { StringContent?: string; Parts?: { text?: string }[] }
    if (contentObj.StringContent) return contentObj.StringContent
    if (contentObj.Parts) {
      return contentObj.Parts.map((p: { text?: string }) => p.text || '').join('')
    }
    return JSON.stringify(content, null, 2)
  }
  return ''
}

// Helper function to parse tool_calls from message object
const parseToolCalls = (toolCalls: unknown, toolResultsMap?: Map<string, { toolName: string; result: unknown }>): ToolCallResult[] => {
  if (!toolCalls) return []

  let parsedToolCalls: Array<{ id: string; type: string; function: { name: string; arguments: string } }> = []

  if (typeof toolCalls === 'string') {
    try {
      parsedToolCalls = JSON.parse(toolCalls)
    } catch {
      return []
    }
  } else if (Array.isArray(toolCalls)) {
    parsedToolCalls = toolCalls
  }

  return parsedToolCalls.map((tc, idx) => {
    const id = tc.id || `tool_${idx}_${Date.now()}`
    const toolName = tc.function?.name || 'unknown'
    let result: unknown = undefined

    // Try to get result from toolResultsMap by tool name
    if (toolResultsMap && toolResultsMap.has(toolName)) {
      result = toolResultsMap.get(toolName)!.result
    }

    return {
      id: id,
      toolName: toolName,
      arguments: (() => {
        try {
          return typeof tc.function?.arguments === 'string'
            ? JSON.parse(tc.function.arguments)
            : tc.function?.arguments || {}
        } catch {
          return {}
        }
      })(),
      result: result,
      status: 'success' as const
    }
  })
}

// Extract chat messages from request/response
const chatMessages = computed(() => {
  if (!logDetail.value?.detail) return []
  const messages: {
    role: string
    content: string
    thinkContent?: string
    hasThink?: boolean
    toolCalls?: ToolCallResult[]
  }[] = []

  // First pass: collect all tool results from messages
  // Format: "Tool: xxx\nResult: xxx" (can be in role: 'tool' or role: 'user')
  const toolResultsMap: Map<string, { toolName: string; result: unknown }> = new Map()

  // Collect tool results from request body
  try {
    const request = logDetail.value.detail.requestBody
    if (request) {
      const reqObj = typeof request === 'string' ? JSON.parse(request) : request

      // Handle messages array
      const msgs = reqObj.messages || reqObj.input
      if (Array.isArray(msgs)) {
        msgs.forEach((msg: { role?: string; content?: string | object }) => {
          if (msg.role === 'tool' || (msg.role === 'user' && typeof msg.content === 'string' && msg.content.startsWith('Tool: '))) {
            const content = typeof msg.content === 'string' ? msg.content : ''
            // Parse "Tool: name\nResult: content" format
            const lines = content.split('\n')
            if (lines.length >= 2 && lines[0].startsWith('Tool: ')) {
              const toolName = lines[0].slice(6).trim()
              let resultPart = lines.slice(1).join('\n').trim()
              if (resultPart.startsWith('Result: ')) {
                resultPart = resultPart.slice(8).trim()
              }
              // Try to parse as JSON
              let result: unknown
              try {
                result = JSON.parse(resultPart)
              } catch {
                result = resultPart
              }
              toolResultsMap.set(toolName, { toolName, result })
            }
          }
        })
      }
    }
  } catch {
    // Ignore parse errors
  }

  // Collect tool results from response body (function_call_output)
  try {
    const response = logDetail.value.detail.responseBody
    if (response) {
      const respObj = typeof response === 'string' ? JSON.parse(response) : response
      if (respObj.output && Array.isArray(respObj.output)) {
        respObj.output.forEach((item: { type?: string; call_id?: string; output?: string; name?: string }) => {
          if (item.type === 'function_call_output' && (item.call_id || item.name)) {
            const key = item.name || item.call_id || ''
            try {
              toolResultsMap.set(key, { toolName: key, result: JSON.parse(item.output || '{}') })
            } catch {
              toolResultsMap.set(key, { toolName: key, result: item.output })
            }
          }
        })
      }
    }
  } catch {
    // Ignore parse errors
  }

  // Second pass: build chat messages
  try {
    const request = logDetail.value.detail.requestBody
    if (request) {
      const reqObj = typeof request === 'string' ? JSON.parse(request) : request

      // Handle Responses API format (input field)
      if (reqObj.input) {
        if (reqObj.instructions) {
          messages.push({ role: 'system', content: reqObj.instructions })
        }
        if (typeof reqObj.input === 'string') {
          messages.push({ role: 'user', content: reqObj.input })
        } else if (Array.isArray(reqObj.input)) {
          reqObj.input.forEach((item: { type?: string; role?: string; content?: string | object; tool_calls?: unknown }) => {
            if (item.role === 'tool' || (item.role === 'user' && typeof item.content === 'string' && item.content?.startsWith('Tool: '))) return
            if (item.role === 'system') return

            if (item.type === 'message' || item.role) {
              const contentText = extractContentText(item.content)
              const parsed = parseMessageContent(contentText)
              const msg: { role: string; content: string; thinkContent?: string; hasThink?: boolean; toolCalls?: ToolCallResult[] } = {
                role: item.role || 'user',
                content: parsed.textContent,
                thinkContent: parsed.thinkContent || undefined,
                hasThink: parsed.hasThink
              }
              if (item.tool_calls) {
                const toolCalls = parseToolCalls(item.tool_calls, toolResultsMap)
                if (toolCalls.length > 0) msg.toolCalls = toolCalls
              }
              messages.push(msg)
            }
          })
        }
      }
      // Handle Chat Completions API format (messages field)
      else if (reqObj.messages && Array.isArray(reqObj.messages)) {
        reqObj.messages.forEach((msg: { role: string; content: string | object; tool_calls?: unknown }) => {
          // Skip tool result messages
          if (msg.role === 'tool' || (msg.role === 'user' && typeof msg.content === 'string' && msg.content?.startsWith('Tool: '))) return

          const contentText = extractContentText(msg.content)
          const parsed = parseMessageContent(contentText)
          const parsedMsg: { role: string; content: string; thinkContent?: string; hasThink?: boolean; toolCalls?: ToolCallResult[] } = {
            role: msg.role,
            content: parsed.textContent,
            thinkContent: parsed.thinkContent || undefined,
            hasThink: parsed.hasThink
          }
          if (msg.tool_calls) {
            const toolCalls = parseToolCalls(msg.tool_calls, toolResultsMap)
            if (toolCalls.length > 0) parsedMsg.toolCalls = toolCalls
          }
          // If this is an assistant message with think content but no tool_calls,
          // and we have tool results collected, attach them here
          if (msg.role === 'assistant' && !parsedMsg.toolCalls && toolResultsMap.size > 0) {
            parsedMsg.toolCalls = Array.from(toolResultsMap.values()).map(tr => ({
              id: `tool_${tr.toolName}_${Date.now()}`,
              toolName: tr.toolName,
              arguments: {},
              result: tr.result,
              status: 'success' as const
            }))
          }
          messages.push(parsedMsg)
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
        respObj.output.forEach((item: { type?: string; role?: string; content?: object[]; output_text?: string; tool_calls?: unknown; name?: string; arguments?: string; id?: string }) => {
          if (item.type === 'function_call_output') return

          if (item.type === 'function_call') {
            const toolCalls = parseToolCalls([{
              id: item.id || '',
              type: 'function',
              function: { name: item.name || 'unknown', arguments: item.arguments || '{}' }
            }], toolResultsMap)
            if (toolCalls.length > 0) {
              messages.push({ role: 'assistant', content: '', toolCalls })
            }
            return
          }

          if (item.type === 'message' && (item.content || item.tool_calls)) {
            const text = item.content
              ? item.content.filter((c: { type?: string; text?: string }) => c.type === 'output_text' && c.text).map((c: { text?: string }) => c.text).join('')
              : ''
            const parsed = parseMessageContent(text)
            const msg: { role: string; content: string; thinkContent?: string; hasThink?: boolean; toolCalls?: ToolCallResult[] } = {
              role: item.role || 'assistant',
              content: parsed.textContent,
              thinkContent: parsed.thinkContent || undefined,
              hasThink: parsed.hasThink
            }
            if (item.tool_calls) {
              const toolCalls = parseToolCalls(item.tool_calls, toolResultsMap)
              if (toolCalls.length > 0) msg.toolCalls = toolCalls
            }
            if (text || msg.toolCalls) messages.push(msg)
          }
        })
        if (respObj.output_text && messages.filter(m => m.role === 'assistant').length === 0) {
          const parsed = parseMessageContent(respObj.output_text)
          messages.push({ role: 'assistant', content: parsed.textContent, thinkContent: parsed.thinkContent || undefined, hasThink: parsed.hasThink })
        }
      }
      // Handle Chat Completions API format (choices field)
      else if (respObj.choices && Array.isArray(respObj.choices)) {
        respObj.choices.forEach((choice: { message?: { role: string; content: string | object; reasoning?: string; tool_calls?: unknown } }) => {
          if (choice.message) {
            const contentText = extractContentText(choice.message.content)
            const parsed = parseMessageContent(contentText)
            const msg: { role: string; content: string; thinkContent?: string; hasThink?: boolean; toolCalls?: ToolCallResult[] } = {
              role: choice.message.role,
              content: parsed.textContent,
              thinkContent: parsed.thinkContent || undefined,
              hasThink: parsed.hasThink
            }
            // 处理 reasoning 字段（OpenAI/Ollama 格式的思考内容）
            if (choice.message.reasoning) {
              if (msg.thinkContent) {
                msg.thinkContent = choice.message.reasoning + '\n' + msg.thinkContent
              } else {
                msg.thinkContent = choice.message.reasoning
              }
              msg.hasThink = true
            }
            if (choice.message.tool_calls) {
              const toolCalls = parseToolCalls(choice.message.tool_calls, toolResultsMap)
              if (toolCalls.length > 0) msg.toolCalls = toolCalls
            }
            messages.push(msg)
          }
        })
      }
    }
  } catch {
    // Ignore parse errors
  }

  return messages
})

// Tool call helper functions
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
  max-height: 500px;
  overflow-y: auto;
  padding: 20px 16px;
  background: #fafafa;
}

/* Message blocks */
.message-block {
  margin-bottom: 20px;
}
.message-block::after {
  content: '';
  display: block;
  clear: both;
}

/* User message - right aligned */
.user-message {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}
.user-bubble {
  max-width: 80%;
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  color: white;
  padding: 12px 16px;
  border-radius: 18px;
  border-bottom-right-radius: 4px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.25);
}

/* System message - right aligned like user but different style */
.system-message {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}
.system-bubble {
  max-width: 80%;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  color: #78350f;
  padding: 12px 16px;
  border-radius: 18px;
  border-bottom-right-radius: 4px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
  box-shadow: 0 2px 8px rgba(245, 158, 11, 0.2);
}
.system-label-text {
  font-size: 11px;
  font-weight: 600;
  color: #b45309;
  margin-bottom: 4px;
}
.system-content {
  font-size: 13px;
  line-height: 1.5;
}

/* Assistant message */
.assistant-message {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 16px;
}
.assistant-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  color: white;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(34, 197, 94, 0.3);
}
.assistant-content {
  flex: 1;
  min-width: 0;
}
.assistant-name {
  font-size: 12px;
  font-weight: 600;
  color: #22c55e;
  margin-bottom: 6px;
}
.assistant-bubble {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  border-top-left-radius: 4px;
  padding: 12px 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

/* Markdown content inside assistant bubble */
.assistant-bubble .markdown-content {
  font-size: 14px;
  color: #374151;
}

/* Tool message */
.tool-message {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}
.tool-bubble {
  max-width: 70%;
  background: #f3f4f6;
  border-radius: 12px;
  padding: 10px 16px;
  text-align: center;
}
.tool-label {
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 4px;
}
.tool-content {
  font-size: 13px;
  color: #4b5563;
  word-break: break-word;
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

/* Headers header with collapse support */
.headers-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #bfdbfe;
  font-size: 14px;
  justify-content: space-between;
}
.headers-card-green .headers-header {
  border-color: #bbf7d0;
}

/* Meta card for metadata mode */
.meta-card {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 12px;
}
.meta-header {
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
.meta-body {
  background: #fafafa;
  padding: 16px;
  font-size: 12px;
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Consolas', monospace;
  overflow: auto;
  max-height: 400px;
  margin: 0;
  color: #4b5563;
  white-space: pre;
  word-break: break-all;
}
.meta-body :deep(.hljs) {
  background: transparent;
  color: #4b5563;
}
.meta-body :deep(.hljs-keyword) { color: #0000ff; }
.meta-body :deep(.hljs-string) { color: #a31515; }
.meta-body :deep(.hljs-number) { color: #098658; }
.meta-body :deep(.hljs-boolean) { color: #0000ff; }
.meta-body :deep(.hljs-null) { color: #0000ff; }
.meta-body :deep(.hljs-attr) { color: #0451a5; }
.meta-body :deep(.hljs-punctuation) { color: #4b5563; }

/* Rotate animation for collapse icon */
.rotate-180 {
  transform: rotate(180deg);
}
.transition-transform {
  transition: transform 0.2s ease;
}
</style>
