<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex justify-between items-center">
      <h2 class="text-xl font-semibold">{{ t('log.title') }}</h2>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-2 items-center text-sm">
      <el-select v-model="filters.model" placeholder="模型" clearable filterable class="!w-32 sm:!w-40" size="small">
        <el-option v-for="model in filterOptions.models" :key="model" :label="model" :value="model" />
      </el-select>
      <el-select v-model="filters.provider" placeholder="提供商" clearable filterable class="!w-24 sm:!w-32" size="small">
        <el-option v-for="provider in filterOptions.providers" :key="provider" :label="provider" :value="provider" />
      </el-select>
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
    <div v-if="pagination.total > 0 || hasFilters" class="flex justify-center mt-6">
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
        <div v-if="chatMessages.length > 0" class="chat-messages-area">
          <div
            v-for="(msg, idx) in chatMessages"
            :key="idx"
            class="log-message-block"
            :class="msg.role"
          >
            <!-- User Message -->
            <div v-if="msg.role === 'user'" class="log-user-message">
              <div class="log-user-avatar">
                <el-icon><User /></el-icon>
              </div>
              <div class="log-user-content">
                <div class="log-user-header">
                  <span class="log-user-name">用户</span>
                  <div class="log-message-actions">
                    <el-tooltip content="复制原文" placement="top">
                      <button class="log-action-btn" @click.stop="copyMessage('text', msg)">
                        <el-icon><Document /></el-icon>
                      </button>
                    </el-tooltip>
                    <el-tooltip content="复制MD" placement="top">
                      <button class="log-action-btn" @click.stop="copyMessage('markdown', msg)">
                        <el-icon><DocumentCopy /></el-icon>
                      </button>
                    </el-tooltip>
                  </div>
                </div>
                <!-- 图片部分 -->
                <div v-if="msg.imageParts && msg.imageParts.length > 0" class="log-image-blocks">
                  <AttachmentPreview v-for="part in msg.imageParts" :key="part.image_url?.url" :part="part" />
                </div>
                <!-- Tool Results (用户发送的工具调用结果) -->
                <div v-if="msg.toolResults && msg.toolResults.length > 0" class="log-tool-results">
                  <div v-for="result in msg.toolResults" :key="result.toolUseId" class="log-tool-result-card">
                    <div class="log-tool-result-header" @click="toggleToolResult(result.toolUseId)">
                      <div class="log-tool-result-icon">
                        <el-icon><Check /></el-icon>
                      </div>
                      <span class="log-tool-result-name">{{ result.toolName || '工具结果' }}</span>
                      <el-icon class="log-tool-expand-icon">
                        <ArrowDown v-if="!expandedToolResults.has(result.toolUseId)" />
                        <ArrowUp v-else />
                      </el-icon>
                    </div>
                    <div v-show="expandedToolResults.has(result.toolUseId)" class="log-tool-result-content">
                      <pre class="log-tool-result-pre">{{ result.content }}</pre>
                    </div>
                  </div>
                </div>
                <!-- System Reminder -->
                  <SystemReminderBlock
                    v-if="extractSystemReminders(msg.content)"
                    :content="extractSystemReminders(msg.content)"
                    :default-collapsed="false"
                  />
                  <!-- Think Block -->
                  <ThinkBlock
                    v-if="parseMessageWithThink(removeSystemReminders(msg.content)).hasThink"
                    :content="parseMessageWithThink(removeSystemReminders(msg.content)).thinkContent"
                    :tokens="estimateThinkTokens(parseMessageWithThink(removeSystemReminders(msg.content)).thinkContent)"
                    :default-collapsed="true"
                  />
                  <!-- 文本内容 -->
                  <div v-if="parseMessageWithThink(removeSystemReminders(msg.content)).textContent" class="log-user-collapsible-bubble">
                    <div class="bubble-header" @click="toggleBubble(`user-${idx}`)">
                      <div class="bubble-icon">
                        <el-icon><User /></el-icon>
                      </div>
                      <div class="bubble-meta">
                        <span class="bubble-label">用户消息</span>
                        <span v-if="!expandedBubbles.has(`user-${idx}`)" class="bubble-preview-text">{{ getBubblePreview(parseMessageWithThink(removeSystemReminders(msg.content)).textContent) }}</span>
                      </div>
                      <el-icon class="bubble-expand-icon">
                        <ArrowDown v-if="!expandedBubbles.has(`user-${idx}`)" />
                        <ArrowUp v-else />
                      </el-icon>
                    </div>
                    <div v-show="expandedBubbles.has(`user-${idx}`)" class="bubble-content">
                      {{ parseMessageWithThink(removeSystemReminders(msg.content)).textContent }}
                    </div>
                  </div>
              </div>
            </div>

            <!-- System Message -->
            <div v-else-if="msg.role === 'system'" class="log-system-block-wrapper">
              <SystemBlock :content="msg.content" :default-collapsed="true" />
              <div class="log-system-actions">
                <el-tooltip content="复制原文" placement="top">
                  <button class="log-action-btn" @click.stop="copyMessage('text', msg)">
                    <el-icon><Document /></el-icon>
                  </button>
                </el-tooltip>
              </div>
            </div>

            <!-- Assistant Message -->
            <div v-else-if="msg.role === 'assistant'" class="log-assistant-message">
              <div class="log-assistant-avatar">
                <el-icon><Monitor /></el-icon>
              </div>
              <div class="log-assistant-content">
                <div class="log-assistant-header">
                  <span class="log-assistant-name">AI</span>
                  <div class="log-message-actions">
                    <el-tooltip content="复制原文" placement="top">
                      <button class="log-action-btn" @click.stop="copyMessage('text', msg)">
                        <el-icon><Document /></el-icon>
                      </button>
                    </el-tooltip>
                    <el-tooltip content="复制MD" placement="top">
                      <button class="log-action-btn" @click.stop="copyMessage('markdown', msg)">
                        <el-icon><DocumentCopy /></el-icon>
                      </button>
                    </el-tooltip>
                  </div>
                </div>
                <!-- System Reminder -->
                <SystemReminderBlock
                  v-if="extractSystemReminders(msg.content)"
                    :content="extractSystemReminders(msg.content)"
                    :default-collapsed="false"
                  />
                  <!-- Think Block -->
                  <ThinkBlock
                    v-if="parseMessageWithThink(removeSystemReminders(msg.content)).hasThink || msg.hasThink"
                    :content="msg.thinkContent || parseMessageWithThink(removeSystemReminders(msg.content)).thinkContent"
                    :tokens="estimateThinkTokens(msg.thinkContent || parseMessageWithThink(removeSystemReminders(msg.content)).thinkContent)"
                    :default-collapsed="true"
                  />
                  <!-- Tool Calls Display -->
                  <ToolCallDisplay
                    v-if="msg.toolCalls && msg.toolCalls.length > 0"
                    :tool-calls="msg.toolCalls"
                    :request-messages="requestMessages"
                  />
                  <!-- Content -->
                  <div v-if="parseMessageWithThink(removeSystemReminders(msg.content)).textContent" class="log-assistant-collapsible-bubble">
                    <div class="bubble-header" @click="toggleBubble(`assistant-${idx}`)">
                      <div class="bubble-icon">
                        <el-icon><Monitor /></el-icon>
                      </div>
                      <div class="bubble-meta">
                        <span class="bubble-label">AI 回复</span>
                        <span v-if="!expandedBubbles.has(`assistant-${idx}`)" class="bubble-preview-text">{{ getBubblePreview(parseMessageWithThink(removeSystemReminders(msg.content)).textContent) }}</span>
                      </div>
                      <el-icon class="bubble-expand-icon">
                        <ArrowDown v-if="!expandedBubbles.has(`assistant-${idx}`)" />
                        <ArrowUp v-else />
                      </el-icon>
                    </div>
                    <div v-show="expandedBubbles.has(`assistant-${idx}`)" class="bubble-content">
                      <MarkdownRenderer :content="parseMessageWithThink(removeSystemReminders(msg.content)).textContent" />
                    </div>
                  </div>
              </div>
            </div>
          </div>
        </div>
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
import { ElMessage } from 'element-plus'
import { CopyDocument, Warning, Loading, Monitor, Document, ChatDotRound, DataLine, User, DocumentCopy, ArrowDown, ArrowUp, Check } from '@element-plus/icons-vue'
import { logApi } from '@/api/log'
import type { Log, LogDetail } from '@/types/log'
import type { ToolCallResult } from '@/types/tool'
import type { ChatContentPart } from '@/types/conversation'
import { parseMessageContent, estimateThinkTokens } from '@/utils/messageParser'
import ThinkBlock from '@/components/chat/ThinkBlock.vue'
import ToolCallDisplay from '@/components/chat/ToolCallDisplay.vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import AttachmentPreview from '@/components/chat/AttachmentPreview.vue'
import SystemBlock from '@/components/chat/SystemBlock.vue'
import SystemReminderBlock from '@/components/chat/SystemReminderBlock.vue'
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

// 从 requestBody 中提取原始请求消息（用于 YOLO 等工具重新绘制）
const requestMessages = computed(() => {
  if (!logDetail.value?.detail?.requestBody) return []
  try {
    const request = logDetail.value.detail.requestBody
    const reqObj = typeof request === 'string' ? JSON.parse(request) : request
    const msgs = reqObj.messages || reqObj.input
    if (Array.isArray(msgs)) {
      return msgs.map((msg: { role?: string; content?: string | object }) => ({
        role: msg.role || 'user',
        content: msg.content || ''
      }))
    }
  } catch {
    // Ignore parse errors
  }
  return []
})

// 折叠状态
const requestHeadersCollapsed = ref(true)
const responseHeadersCollapsed = ref(true)
const expandedToolResults = ref<Set<string>>(new Set())
const expandedBubbles = ref<Set<string>>(new Set())

// Toggle tool result collapse
const toggleToolResult = (toolUseId: string) => {
  if (expandedToolResults.value.has(toolUseId)) {
    expandedToolResults.value.delete(toolUseId)
  } else {
    expandedToolResults.value.add(toolUseId)
  }
}

// Toggle bubble collapse
const toggleBubble = (bubbleId: string) => {
  if (expandedBubbles.value.has(bubbleId)) {
    expandedBubbles.value.delete(bubbleId)
  } else {
    expandedBubbles.value.add(bubbleId)
  }
}

// Get preview text for collapsed bubble
const getBubblePreview = (content: string): string => {
  const maxLen = 100
  return content.length > maxLen ? content.slice(0, maxLen) + '...' : content
}

// Initialize bubble collapse state
const initBubbleCollapse = () => {
  expandedBubbles.value = new Set()
}

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
  fetchFilterOptions()
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

// 筛选器选项（从后端获取）
const filterOptions = reactive({
  models: [] as string[],
  providers: [] as string[]
})

// 计算是否有筛选条件
const hasFilters = computed(() => {
  return filters.model || filters.provider || filters.status || filters.dateRange
})

// 获取筛选器选项
const fetchFilterOptions = async () => {
  try {
    const response = await logApi.getFilters()
    filterOptions.models = response.data.models || []
    filterOptions.providers = response.data.providers || []
  } catch (error) {
    console.error('Failed to fetch filter options:', error)
  }
}

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

const copyToClipboard = async (text: string | object | null | undefined) => {
  if (!text) return
  try {
    await navigator.clipboard.writeText(typeof text === 'string' ? text : JSON.stringify(text, null, 2))
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

// Copy message content
const copyMessage = async (format: string, msg: { role: string; content: string; thinkContent?: string }) => {
  let text = ''
  if (format === 'text') {
    // Plain text format
    if (msg.thinkContent) {
      text = `[思考]\n${msg.thinkContent}\n\n[回复]\n${msg.content}`
    } else {
      text = msg.content
    }
  } else if (format === 'markdown') {
    // Markdown format
    if (msg.role === 'user') {
      text = `**用户:**\n\n${msg.content}`
    } else if (msg.role === 'assistant') {
      if (msg.thinkContent) {
        text = `**AI:**\n\n<details>\n<summary>思考过程</summary>\n\n${msg.thinkContent}\n\n</details>\n\n${msg.content}`
      } else {
        text = `**AI:**\n\n${msg.content}`
      }
    } else {
      text = `**System:**\n\n${msg.content}`
    }
  }
  await copyToClipboard(text)
}

// Helper function to extract text from content
const extractContentText = (content: string | object | undefined): string => {
  if (!content) return ''
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    // Handle [{type: "text", text: "..."}] format (Anthropic/OpenAI multimodal)
    return content
      .map((item: { type?: string; text?: string; thinking?: string }) => {
        if (item.type === 'text' && item.text) return item.text
        if (item.type === 'thinking' && item.thinking) return `[思考] ${item.thinking}`
        // image_url type is handled separately via extractImageParts
        // tool_use and tool_result are handled separately via toolCalls array
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

// Helper function to extract image parts from content
const extractImageParts = (content: string | object | undefined): ChatContentPart[] => {
  if (!content) return []
  if (typeof content === 'string') return []
  if (Array.isArray(content)) {
    return content
      .flatMap((item: { type?: string; image_url?: { url?: string; detail?: string }; source?: { type?: string; media_type?: string; data?: string } }) => {
        // OpenAI-style: { type: "image_url", image_url: { url, detail } }
        if (item.type === 'image_url' && item.image_url?.url) {
          return {
            type: 'image_url' as const,
            image_url: {
              url: item.image_url.url,
              detail: item.image_url?.detail || undefined
            }
          }
        }
        // Anthropic-style: { type: "image", source: { type: "base64", media_type, data } }
        if (item.type === 'image' && item.source?.type === 'base64') {
          const mediaType = item.source.media_type || 'image/jpeg'
          const dataUrl = `data:${mediaType};base64,${item.source.data}`
          return {
            type: 'image_url' as const,
            image_url: { url: dataUrl }
          }
        }
        return []
      })
  }
  return []
}

// Helper function to extract system-reminder content from message
const extractSystemReminders = (content: string | undefined): string => {
  if (!content) return ''
  const matches = content.match(/<system-reminder>\s*[\s\S]*?\s*<\/system-reminder>/gi)
  return matches ? matches.join('\n') : ''
}

// Helper function to remove system-reminder tags from content
const removeSystemReminders = (content: string | undefined): string => {
  if (!content) return ''
  return content.replace(/<system-reminder>\s*[\s\S]*?\s*<\/system-reminder>/gi, '').trim()
}

// Helper function to parse message content with think tags
const parseMessageWithThink = (content: string | undefined): { textContent: string; thinkContent: string; hasThink: boolean } => {
  if (!content) return { textContent: '', thinkContent: '', hasThink: false }
  const parsed = parseMessageContent(content)
  return {
    textContent: parsed.textContent,
    thinkContent: parsed.thinkContent || '',
    hasThink: parsed.hasThink
  }
}

// Helper function to parse tool_calls from message object
const parseToolCalls = (toolCalls: unknown, toolResultsMap?: Map<string, { toolName?: string; result: unknown; isError?: boolean }>): ToolCallResult[] => {
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
    let status: 'success' | 'error' = 'success'

    // Try to get result from toolResultsMap by id or tool name
    if (toolResultsMap) {
      if (toolResultsMap.has(id)) {
        const toolResult = toolResultsMap.get(id)!
        result = toolResult.result
        if (toolResult.isError) status = 'error'
      } else if (toolResultsMap.has(toolName)) {
        result = toolResultsMap.get(toolName)!.result
      }
    }

    // Parse arguments
    let args: Record<string, unknown> = {}
    if (tc.function?.arguments) {
      try {
        args = typeof tc.function.arguments === 'string'
          ? JSON.parse(tc.function.arguments)
          : tc.function.arguments
      } catch {
        args = { raw: tc.function.arguments }
      }
    }

    return {
      id,
      toolName,
      arguments: args,
      result,
      status
    }
  })
}

// Type for parsed chat message
type ParsedChatMessage = {
  role: string
  content: string
  thinkContent?: string
  hasThink?: boolean
  toolCalls?: ToolCallResult[]
  toolResults?: Array<{ toolUseId: string; toolName?: string; content: string; isError?: boolean }>
  imageParts?: ChatContentPart[]
  rawContent?: string | object
  isToolResultOnly?: boolean
}

// Extract chat messages from request/response
const chatMessages = computed(() => {
  if (!logDetail.value?.detail) return []
  const messages: ParsedChatMessage[] = []

  // First pass: collect all tool results from messages by tool_use_id
  const toolResultsMap: Map<string, { toolName?: string; result: unknown; isError?: boolean }> = new Map()
  // Also collect tool_use info by id for matching
  const toolUseMap: Map<string, { toolName: string; input: unknown }> = new Map()

  // Collect tool results from request body
  try {
    const request = logDetail.value.detail.requestBody
    if (request) {
      const reqObj = typeof request === 'string' ? JSON.parse(request) : request

      // Handle messages array
      const msgs = reqObj.messages || reqObj.input
      if (Array.isArray(msgs)) {
        msgs.forEach((msg: { role?: string; content?: string | object }) => {
          // Handle Anthropic tool_result in content array
          if (Array.isArray(msg.content)) {
            msg.content.forEach((block: { type?: string; tool_use_id?: string; content?: unknown; is_error?: boolean; name?: string; id?: string; input?: unknown }) => {
              if (block.type === 'tool_result' && block.tool_use_id) {
                // Parse content if it's a JSON string
                let parsedContent = block.content
                if (typeof block.content === 'string') {
                  try {
                    parsedContent = JSON.parse(block.content)
                  } catch {
                    // Keep as string if not valid JSON
                  }
                }
                toolResultsMap.set(block.tool_use_id, {
                  result: parsedContent,
                  isError: block.is_error
                })
              }
              if (block.type === 'tool_use' && block.id) {
                toolUseMap.set(block.id, {
                  toolName: block.name || 'unknown',
                  input: block.input
                })
              }
            })
          }
          // Handle tool role with string content (OpenAI format)
          if (msg.role === 'tool' && typeof msg.content === 'string') {
            const content = msg.content
            // Try to parse as JSON first
            let parsedContent: unknown = content
            try {
              parsedContent = JSON.parse(content)
            } catch {
              // Keep as string if not valid JSON
            }
            // Try to match with tool_call_id if available
            const toolCallId = (msg as { tool_call_id?: string }).tool_call_id
            if (toolCallId) {
              toolResultsMap.set(toolCallId, {
                result: parsedContent
              })
            }
          }
        })
      }
    }
  } catch {
    // Ignore parse errors
  }

  // Second pass: build messages, matching tool_use with tool_result
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
            if (item.role === 'tool' || item.role === 'system') return

            if (item.type === 'message' || item.role) {
              const contentText = extractContentText(item.content)
              const parsed = parseMessageContent(contentText)
              const msg: ParsedChatMessage = {
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
        // Handle Anthropic system field
        if (reqObj.system) {
          const systemText = typeof reqObj.system === 'string'
            ? reqObj.system
            : extractContentText(reqObj.system)
          if (systemText) {
            messages.push({ role: 'system', content: systemText })
          }
        }
        reqObj.messages.forEach((msg: { role: string; content: string | object; tool_calls?: unknown }) => {
          // Skip tool role messages - they will be matched with tool_calls
          if (msg.role === 'tool') return

          // Handle array content (Anthropic-style with thinking, text, tool_use, tool_result)
          if (Array.isArray(msg.content)) {
            let textContent = ''
            let thinkContent = ''
            const toolCalls: ToolCallResult[] = []
            const toolResults: Array<{ toolUseId: string; toolName?: string; content: string; isError?: boolean }> = []
            const imageParts: ChatContentPart[] = []
            let hasToolResultOnly = true  // Check if message is only tool_result

            msg.content.forEach((block: { type?: string; text?: string; thinking?: string; name?: string; input?: unknown; id?: string; image_url?: { url?: string }; source?: { type?: string; media_type?: string; data?: string }; tool_use_id?: string; content?: unknown; is_error?: boolean }) => {
              if (block.type === 'text' && block.text) {
                textContent += block.text
                hasToolResultOnly = false
              } else if (block.type === 'thinking' && block.thinking) {
                thinkContent += block.thinking
                hasToolResultOnly = false
              } else if (block.type === 'tool_use' && block.name && block.id) {
                // Match tool_use with tool_result using tool_use_id
                const toolResult = toolResultsMap.get(block.id)
                toolCalls.push({
                  id: block.id,
                  toolName: block.name,
                  arguments: (block.input as Record<string, unknown>) || {},
                  result: toolResult?.result,
                  status: toolResult?.isError ? 'error' : 'success'
                })
                hasToolResultOnly = false
              } else if (block.type === 'tool_result' && block.tool_use_id) {
                // This is a tool_result in user message
                const toolUseInfo = toolUseMap.get(block.tool_use_id)
                const resultContent = typeof block.content === 'string' ? block.content : JSON.stringify(block.content)
                toolResults.push({
                  toolUseId: block.tool_use_id,
                  toolName: toolUseInfo?.toolName,
                  content: resultContent,
                  isError: block.is_error
                })
              } else if (block.type === 'image_url' && block.image_url?.url) {
                imageParts.push({
                  type: 'image_url',
                  image_url: { url: block.image_url.url }
                })
                hasToolResultOnly = false
              } else if (block.type === 'image' && block.source?.type === 'base64') {
                // Anthropic-style image: { type: "image", source: { type: "base64", media_type, data } }
                const mediaType = block.source.media_type || 'image/jpeg'
                const dataUrl = `data:${mediaType};base64,${block.source.data}`
                imageParts.push({
                  type: 'image_url',
                  image_url: { url: dataUrl }
                })
                hasToolResultOnly = false
              }
            })

            const parsed = parseMessageContent(textContent)
            const parsedMsg: ParsedChatMessage = {
              role: msg.role,
              content: parsed.textContent,
              thinkContent: thinkContent || parsed.thinkContent || undefined,
              hasThink: !!thinkContent || parsed.hasThink,
              rawContent: msg.content,
              isToolResultOnly: hasToolResultOnly && toolResults.length > 0
            }
            if (imageParts.length > 0) {
              parsedMsg.imageParts = imageParts
            }
            if (toolCalls.length > 0) {
              parsedMsg.toolCalls = toolCalls
            }
            if (toolResults.length > 0) {
              parsedMsg.toolResults = toolResults
            }
            if (msg.tool_calls) {
              const extraToolCalls = parseToolCalls(msg.tool_calls, toolResultsMap)
              if (extraToolCalls.length > 0 && !parsedMsg.toolCalls) {
                parsedMsg.toolCalls = extraToolCalls
              }
            }
            // Only push if has content or tool info
            if (textContent || thinkContent || toolCalls.length > 0 || toolResults.length > 0 || imageParts.length > 0) {
              messages.push(parsedMsg)
            }
            return
          }

          // Standard string content
          const contentText = extractContentText(msg.content)
          const imageParts = extractImageParts(msg.content)
          const parsed = parseMessageContent(contentText)
          const parsedMsg: ParsedChatMessage = {
            role: msg.role,
            content: parsed.textContent,
            thinkContent: parsed.thinkContent || undefined,
            hasThink: parsed.hasThink,
            rawContent: msg.content
          }
          if (imageParts.length > 0) {
            parsedMsg.imageParts = imageParts
          }

          // Extract tool_calls from OpenAI format
          if (msg.tool_calls) {
            const toolCalls = parseToolCalls(msg.tool_calls, toolResultsMap)
            if (toolCalls.length > 0) parsedMsg.toolCalls = toolCalls
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
            // Handle array content (Anthropic-style in OpenAI format)
            if (Array.isArray(choice.message.content)) {
              let textContent = ''
              let thinkContent = ''
              const toolCalls: ToolCallResult[] = []

              choice.message.content.forEach((block: { type?: string; text?: string; thinking?: string; name?: string; input?: unknown; id?: string }) => {
                if (block.type === 'text' && block.text) {
                  textContent += block.text
                } else if (block.type === 'thinking' && block.thinking) {
                  thinkContent += block.thinking
                } else if (block.type === 'tool_use' && block.name && block.id) {
                  // Match tool_use with tool_result using tool_use_id
                  const toolResult = toolResultsMap.get(block.id)
                  toolCalls.push({
                    id: block.id,
                    toolName: block.name,
                    arguments: (block.input as Record<string, unknown>) || {},
                    result: toolResult?.result,
                    status: toolResult?.isError ? 'error' as const : 'success' as const
                  })
                }
              })

              const parsed = parseMessageContent(textContent)
              const msg: { role: string; content: string; thinkContent?: string; hasThink?: boolean; toolCalls?: ToolCallResult[] } = {
                role: choice.message.role,
                content: parsed.textContent,
                thinkContent: thinkContent || parsed.thinkContent || undefined,
                hasThink: !!thinkContent || parsed.hasThink
              }
              if (toolCalls.length > 0) {
                msg.toolCalls = toolCalls
              }
              if (choice.message.tool_calls) {
                const extraToolCalls = parseToolCalls(choice.message.tool_calls, toolResultsMap)
                if (extraToolCalls.length > 0 && !msg.toolCalls) {
                  msg.toolCalls = extraToolCalls
                }
              }
              messages.push(msg)
            } else {
              // Standard string content
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
          }
        })
      }
      // Handle Anthropic Messages API format (content field with type: "message")
      else if (respObj.type === 'message' && respObj.content && Array.isArray(respObj.content)) {
        let textContent = ''
        let thinkContent = ''
        const toolCalls: ToolCallResult[] = []

        respObj.content.forEach((block: { type?: string; text?: string; thinking?: string; name?: string; input?: unknown; id?: string }) => {
          if (block.type === 'text' && block.text) {
            textContent += block.text
          } else if (block.type === 'thinking' && block.thinking) {
            thinkContent += block.thinking
          } else if (block.type === 'tool_use' && block.name && block.id) {
            // Match tool_use with tool_result using tool_use_id
            const toolResult = toolResultsMap.get(block.id)
            toolCalls.push({
              id: block.id,
              toolName: block.name,
              arguments: block.input as Record<string, unknown> || {},
              result: toolResult?.result,
              status: toolResult?.isError ? 'error' as const : 'success' as const
            })
          }
        })

        const parsed = parseMessageContent(textContent)
        const msg: { role: string; content: string; thinkContent?: string; hasThink?: boolean; toolCalls?: ToolCallResult[] } = {
          role: 'assistant',
          content: parsed.textContent,
        }
        if (thinkContent || parsed.thinkContent) {
          msg.thinkContent = thinkContent + (parsed.thinkContent || '')
          msg.hasThink = true
        }
        if (toolCalls.length > 0) {
          msg.toolCalls = toolCalls
        }
        messages.push(msg)
      }
      // Handle generic content array (without type: "message" wrapper)
      else if (respObj.content && Array.isArray(respObj.content) && !respObj.type) {
        let textContent = ''
        let thinkContent = ''
        const toolCalls: ToolCallResult[] = []

        respObj.content.forEach((block: { type?: string; text?: string; thinking?: string; name?: string; input?: unknown; id?: string }) => {
          if (block.type === 'text' && block.text) {
            textContent += block.text
          } else if (block.type === 'thinking' && block.thinking) {
            thinkContent += block.thinking
          } else if (block.type === 'tool_use' && block.name && block.id) {
            // Match tool_use with tool_result using tool_use_id
            const toolResult = toolResultsMap.get(block.id)
            toolCalls.push({
              id: block.id,
              toolName: block.name,
              arguments: (block.input as Record<string, unknown>) || {},
              result: toolResult?.result,
              status: toolResult?.isError ? 'error' as const : 'success' as const
            })
          }
        })

        const parsed = parseMessageContent(textContent)
        const msg: { role: string; content: string; thinkContent?: string; hasThink?: boolean; toolCalls?: ToolCallResult[] } = {
          role: 'assistant',
          content: parsed.textContent,
        }
        if (thinkContent || parsed.thinkContent) {
          msg.thinkContent = thinkContent + (parsed.thinkContent || '')
          msg.hasThink = true
        }
        if (toolCalls.length > 0) {
          msg.toolCalls = toolCalls
        }
        messages.push(msg)
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
    initBubbleCollapse()
  } catch (error) {
    ElMessage.error(t('common.error'))
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

/* Chat messages area - similar to ChatView */
.chat-messages-area {
  max-height: 500px;
  overflow-y: auto;
  padding: 16px;
  background: linear-gradient(180deg, #fafafa 0%, #f5f5f5 100%);
  border: 1px solid #e5e7eb;
  border-radius: 12px;
}

/* Log message blocks */
.log-message-block {
  margin-bottom: 20px;
}

/* User Message - right aligned with avatar */
.log-user-message {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.log-user-avatar {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
  order: 2;
}

.log-user-content {
  flex: 1;
  min-width: 200px;
  max-width: 70%;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.log-user-header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 4px 0;
  cursor: pointer;
  user-select: none;
  transition: opacity 0.2s;
}

.log-user-header:hover {
  opacity: 0.8;
}

.log-user-name {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
}

.log-user-preview {
  font-size: 12px;
  color: #9ca3af;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-user-body {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.log-expand-icon {
  color: #9ca3af;
  font-size: 14px;
}

.log-image-blocks {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.log-image-blocks :deep(.attachment-preview) {
  display: block;
}

.log-image-blocks :deep(.image-preview) {
  width: 150px;
  height: 150px;
  border-radius: 12px;
}

/* Tool Results - 用户发送的工具调用结果 */
.log-tool-results {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
}

.log-tool-result-card {
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  overflow: hidden;
}

.log-tool-result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.log-tool-result-header:hover {
  background: rgba(34, 197, 94, 0.1);
}

.log-tool-result-icon {
  width: 20px;
  height: 20px;
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  border-radius: 50%;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

.log-tool-result-name {
  flex: 1;
  font-size: 12px;
  font-weight: 500;
  color: #166534;
}

.log-tool-expand-icon {
  color: #22c55e;
  font-size: 14px;
}

.log-tool-result-content {
  padding: 8px 12px;
  border-top: 1px solid #bbf7d0;
  background: rgba(255, 255, 255, 0.5);
}

.log-tool-result-pre {
  margin: 0;
  padding: 8px 10px;
  background: #fff;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #15803d;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
}

.log-tool-result-content {
  font-size: 12px;
  line-height: 1.5;
  color: #15803d;
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(255, 255, 255, 0.5);
  padding: 8px 10px;
  border-radius: 4px;
}

/* User Collapsible Bubble - 类似 ThinkBlock 样式，紫色系 */
.log-user-collapsible-bubble {
  margin: 8px 0;
  border: 1px solid #ddd6fe;
  border-radius: 8px;
  background: linear-gradient(135deg, #f3e8ff 0%, #e9d5ff 100%);
  overflow: hidden;
}

.log-user-collapsible-bubble .bubble-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.log-user-collapsible-bubble .bubble-header:hover {
  background: rgba(168, 85, 247, 0.1);
}

.log-user-collapsible-bubble .bubble-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: linear-gradient(135deg, #a855f7 0%, #9333ea 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

.log-user-collapsible-bubble .bubble-meta {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.log-user-collapsible-bubble .bubble-label {
  font-size: 12px;
  font-weight: 500;
  color: #9333ea;
}

.log-user-collapsible-bubble .bubble-preview-text {
  font-size: 11px;
  color: #7c3aed;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.log-user-collapsible-bubble .bubble-expand-icon {
  color: #a855f7;
  font-size: 14px;
}

.log-user-collapsible-bubble .bubble-content {
  padding: 12px 16px;
  border-top: 1px solid #c4b5fd;
  background: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  line-height: 1.6;
  color: #6b21a8;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Assistant Collapsible Bubble - 类似 ThinkBlock 样式，绿色系 */
.log-assistant-collapsible-bubble {
  margin: 8px 0;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
  overflow: hidden;
}

.log-assistant-collapsible-bubble .bubble-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.log-assistant-collapsible-bubble .bubble-header:hover {
  background: rgba(34, 197, 94, 0.1);
}

.log-assistant-collapsible-bubble .bubble-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

.log-assistant-collapsible-bubble .bubble-meta {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.log-assistant-collapsible-bubble .bubble-label {
  font-size: 12px;
  font-weight: 500;
  color: #166534;
}

.log-assistant-collapsible-bubble .bubble-preview-text {
  font-size: 11px;
  color: #15803d;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 300px;
}

.log-assistant-collapsible-bubble .bubble-expand-icon {
  color: #22c55e;
  font-size: 14px;
}

.log-assistant-collapsible-bubble .bubble-content {
  padding: 12px 16px;
  border-top: 1px solid #86efac;
  background: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  line-height: 1.7;
  color: #1f2937;
}

/* System Message - collapsible block */
.log-system-block-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.log-system-actions {
  display: flex;
  gap: 4px;
  opacity: 0.5;
  transition: opacity 0.2s;
}

.log-system-block-wrapper:hover .log-system-actions {
  opacity: 1;
}

/* Assistant Message - left aligned with avatar */
.log-assistant-message {
  display: flex;
  gap: 12px;
}

.log-assistant-avatar {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}

.log-assistant-content {
  flex: 1;
  min-width: 200px;
  max-width: 85%;
}

.log-assistant-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  cursor: pointer;
  user-select: none;
  transition: opacity 0.2s;
}

.log-assistant-header:hover {
  opacity: 0.8;
}

.log-assistant-name {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
}

.log-assistant-preview {
  flex: 1;
  font-size: 12px;
  color: #9ca3af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}

.log-assistant-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.log-message-actions {
  display: flex;
  gap: 4px;
  opacity: 0.5;
  transition: opacity 0.2s;
}

.log-message-block:hover .log-message-actions {
  opacity: 1;
}

.log-action-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #9ca3af;
  cursor: pointer;
  transition: all 0.2s;
}

.log-action-btn:hover {
  background: #f3f4f6;
  color: #374151;
}

.log-assistant-collapsible-bubble :deep(.markdown-content) {
  font-size: 13px;
  color: #1f2937;
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
