<template>
  <div class="chat-page">
    <!-- Mobile Sidebar Overlay -->
    <div
      v-if="sidebarOpen && isMobile"
      class="sidebar-overlay"
      @click="sidebarOpen = false"
    ></div>

    <!-- Sidebar - Conversation List -->
    <aside class="sidebar" :class="{ open: sidebarOpen || !isMobile }">
      <div class="sidebar-header">
        <span class="sidebar-title">对话历史</span>
        <button class="sidebar-close" @click="sidebarOpen = false" v-if="isMobile">
          <el-icon><Close /></el-icon>
        </button>
      </div>

      <div class="sidebar-content">
        <button class="new-chat-btn" @click="createNewConversation">
          <el-icon><Plus /></el-icon>
          <span>新对话</span>
        </button>

        <div class="conversation-list">
          <div
            v-for="conv in conversations"
            :key="conv.id"
            class="conversation-item"
            :class="{ active: currentConversation?.id === conv.id }"
            @click="selectConversation(conv)"
          >
            <div class="conv-icon">
              <el-icon><ChatLineRound /></el-icon>
            </div>
            <div class="conv-info">
              <div class="conv-title">{{ conv.title }}</div>
              <div class="conv-meta">{{ conv.model }}</div>
            </div>
            <el-dropdown trigger="click" @command="handleConversationAction($event, conv)">
              <button class="conv-more" @click.stop>
                <el-icon><MoreFilled /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="delete">
                    <el-icon><Delete /></el-icon>
                    删除对话
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <div v-if="conversations.length === 0" class="empty-state">
            <el-icon :size="32"><ChatLineRound /></el-icon>
            <p>暂无对话记录</p>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="main-content">
      <!-- Tools Dialog -->
      <ToolsDialog v-model="showToolsDialog" />

      <!-- Header -->
      <header class="chat-header">
        <div class="header-left">
          <button class="menu-btn" @click="sidebarOpen = true" v-if="isMobile && !sidebarOpen">
            <el-icon><Menu /></el-icon>
          </button>

          <!-- Model Selector -->
          <div class="model-selector" v-if="currentConversation">
            <el-select
              v-model="selectedModel"
              placeholder="选择模型"
              size="default"
              @change="updateModel"
            >
              <el-option
                v-for="model in models"
                :key="model.name"
                :label="model.alias || model.name"
                :value="model.name"
              />
            </el-select>
          </div>
          <div class="model-selector" v-else>
            <span class="placeholder-text">选择模型开始对话</span>
          </div>
        </div>

        <div class="header-right">
          <button class="icon-btn" @click="showToolsDialog = true" title="工具">
            <el-icon><Operation /></el-icon>
          </button>
          <button class="icon-btn" @click="showSettingsDialog = true" :disabled="!currentConversation" title="设置">
            <el-icon><Setting /></el-icon>
          </button>
          <button class="primary-btn" @click="createNewConversation">
            <el-icon><Plus /></el-icon>
            <span class="hide-mobile">新对话</span>
          </button>
        </div>
      </header>

      <!-- Messages Area -->
      <div class="messages-area" ref="messagesAreaRef" @scroll="handleScroll">
        <!-- Welcome Screen -->
        <div v-if="!currentConversation" class="welcome-screen">
          <div class="welcome-content">
            <div class="welcome-icon">
              <el-icon :size="48"><Promotion /></el-icon>
            </div>
            <h2>AI 助手</h2>
            <p>选择或创建一个对话开始聊天</p>

            <div class="quick-start">
              <div class="model-select-row">
                <span class="label">模型</span>
                <el-select v-model="selectedModel" placeholder="选择模型" size="large">
                  <el-option
                    v-for="model in models"
                    :key="model.name"
                    :label="model.alias || model.name"
                    :value="model.name"
                  />
                </el-select>
              </div>
              <button class="start-btn" @click="createNewConversation">
                <el-icon><ChatLineRound /></el-icon>
                <span>开始对话</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Messages -->
        <div v-else class="messages-container">
          <div
            v-for="block in expandedMessages"
            :key="block.id"
            class="message-block"
            :class="block.role"
          >
            <!-- User Message Block -->
            <div v-if="block.role === 'user'" class="user-message">
              <!-- 编辑模式 -->
              <div v-if="editingBlockId === block.id && block.type === 'text'" class="user-bubble edit-mode">
                <textarea
                  ref="editTextareaRef"
                  v-model="editingContent"
                  class="edit-textarea"
                  rows="2"
                  @keydown="handleEditKeydown"
                ></textarea>
                <div class="edit-actions">
                  <button class="edit-btn cancel" @click="cancelEdit">取消</button>
                  <button class="edit-btn confirm" @click="confirmEditBlock">发送</button>
                </div>
              </div>
              <!-- 正常显示 -->
              <template v-else>
                <div class="user-bubble">
                  <!-- 图片块 -->
                  <div v-if="block.type === 'image'" class="image-block">
                    <AttachmentPreview :part="block.part!" />
                  </div>
                  <!-- 文本块 -->
                  <div v-else class="user-text">{{ block.content }}</div>
                </div>
              </template>
              <!-- 操作按钮 -->
              <div v-if="editingBlockId !== block.id && !sending" class="message-actions">
                <!-- 文本块：编辑 + 删除 -->
                <template v-if="block.type === 'text'">
                  <button class="action-icon-btn" @click="startEditBlock(block.id, block)" title="编辑">
                    <el-icon><Edit /></el-icon>
                  </button>
                  <button class="action-icon-btn" @click="regenerateFromUser(block.originalIndex)" title="重新生成">
                    <el-icon><RefreshRight /></el-icon>
                  </button>
                </template>
                <!-- 所有块：删除 -->
                <button class="action-icon-btn delete" @click="deleteMessage(block.originalIndex)" title="删除">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
            </div>

            <!-- Assistant Message (exclude tool role messages) -->
            <div v-else-if="block.role !== 'tool'" class="assistant-message">
              <div class="assistant-avatar">
                <el-icon><Monitor /></el-icon>
              </div>
              <div class="assistant-content">
                <div class="assistant-header">
                  <div class="assistant-name">AI</div>
                  <div v-if="!sending" class="message-actions">
                    <button class="action-icon-btn" @click="copyMessage(block.message.content)" title="复制">
                      <el-icon><DocumentCopy /></el-icon>
                    </button>
                    <button class="action-icon-btn delete" @click="deleteMessage(block.originalIndex)" title="删除">
                      <el-icon><Delete /></el-icon>
                    </button>
                  </div>
                </div>
                <!-- Think Block -->
                <ThinkBlock
                  v-if="block.message.hasThink"
                  :content="block.message.thinkContent || ''"
                  :tokens="estimateThinkTokens(block.message.thinkContent || '')"
                  :default-collapsed="true"
                  :force-expand="!block.message.content && (!block.message.toolCalls || block.message.toolCalls.length === 0)"
                />
                <!-- Tool Calls Display -->
                <ToolCallDisplay
                  v-if="block.message.toolCalls && block.message.toolCalls.length > 0"
                  :tool-calls="block.message.toolCalls"
                />
                <!-- Markdown Content -->
                <div v-if="block.message.content" class="assistant-bubble">
                  <MarkdownRenderer :content="block.message.content" />
                </div>
              </div>
            </div>
          </div>

          <!-- Streaming Message -->
          <div v-if="throttledStreamingContent || throttledStreamingThink || streamingToolCallResults.length > 0" class="message-block assistant">
            <div class="assistant-message">
              <div class="assistant-avatar" :class="{ thinking: isAnyToolRunning }">
                <el-icon v-if="isAnyToolRunning" class="is-loading"><Loading /></el-icon>
                <el-icon v-else><Monitor /></el-icon>
              </div>
              <div class="assistant-content">
                <div class="assistant-name">AI</div>
                <!-- Streaming Think Block -->
                <ThinkBlock
                  v-if="throttledStreamingThink"
                  :content="throttledStreamingThink"
                  :default-collapsed="true"
                  :force-expand="!throttledStreamingContent && streamingToolCallResults.length === 0"
                />
                <!-- Streaming Tool Calls Display -->
                <ToolCallDisplay
                  v-if="streamingToolCallResults.length > 0"
                  :tool-calls="streamingToolCallResults"
                />

                <!-- Tool Executing Indicator - show when tools are running and no result yet -->
                <div v-if="isAnyToolRunning" class="tool-executing-indicator">
                  <el-icon class="is-loading"><Loading /></el-icon>
                  <span>正在执行工具...</span>
                </div>

                <!-- Streaming Markdown Content -->
                <div v-if="throttledStreamingContent" class="assistant-bubble">
                  <MarkdownRenderer :content="throttledStreamingContent" />
                  <span class="cursor" v-if="sending">▌</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Thinking State - only show when no streaming content yet AND no tools running -->
          <div v-if="sending && !streamingContent && !streamingThinkContent && streamingToolCallResults.length === 0" class="message-block assistant">
            <div class="assistant-message">
              <div class="assistant-avatar thinking">
                <el-icon class="is-loading"><Loading /></el-icon>
              </div>
              <div class="assistant-content">
                <div class="assistant-name">AI</div>
                <div class="assistant-bubble thinking">
                  <div class="thinking-indicator">
                    <span></span><span></span><span></span>
                  </div>
                  <span class="thinking-text">正在思考...</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Input Area -->
      <div class="input-area">
        <div class="input-container">
          <!-- Enabled Tools Display -->
          <div v-if="toolsStore.enabledTools.length > 0" class="enabled-tools-bar">
            <span class="tools-label">工具:</span>
            <el-tag
              v-for="tool in visibleTools"
              :key="tool.id"
              size="small"
              closable
              @close="toolsStore.toggleTool(tool.id)"
            >
              {{ tool.name }}
            </el-tag>
            <el-tag v-if="hiddenToolsCount > 0" size="small" type="info" class="more-tools-tag">
              +{{ hiddenToolsCount }}
            </el-tag>
          </div>

          <!-- Input Box -->
          <div class="input-box" :class="{ disabled: !currentConversation || sending }">
            <!-- File upload button -->
            <button
              class="upload-btn"
              :disabled="!currentConversation || sending"
              @click="triggerUpload"
              title="上传文件"
            >
              <el-icon><Paperclip /></el-icon>
            </button>
            <input
              ref="fileInputRef"
              type="file"
              accept="*/*"
              multiple
              @change="handleFileUpload"
              style="display: none"
            />

            <!-- Attached files preview -->
            <div v-if="attachedFiles.length > 0" class="attached-files">
              <div v-for="(file, idx) in attachedFiles" :key="idx" class="attached-file">
                <img v-if="file.isImage" :src="file.dataUrl" class="file-preview" />
                <span v-else class="file-name">{{ file.filename }}</span>
                <button class="remove-file" @click="removeFile(idx)">×</button>
              </div>
            </div>

            <textarea
              ref="textareaRef"
              v-model="inputContent"
              placeholder="输入消息... (支持粘贴截图/文件)"
              :disabled="!currentConversation || sending"
              @keydown="handleKeydown"
              @input="autoResize"
              @paste="handlePaste"
              rows="1"
            ></textarea>
            <!-- Stop button (show when streaming) -->
            <button
              v-if="sending"
              class="stop-btn"
              @click="stopStreaming"
              title="停止生成"
            >
              <el-icon><Close /></el-icon>
            </button>
            <!-- Send button -->
            <button
              v-else
              class="send-btn"
              :class="{ active: (inputContent.trim() || attachedFiles.length > 0) && currentConversation }"
              :disabled="(!inputContent.trim() && attachedFiles.length === 0) || !currentConversation"
              @click="sendMessage"
            >
              <el-icon><Promotion /></el-icon>
            </button>
          </div>

          <div class="input-footer">
            <div class="input-actions">
              <el-dropdown trigger="click" @command="applyPreset" v-if="currentConversation && !isMobile">
                <button class="action-btn">
                  <el-icon><MagicStick /></el-icon>
                  <span>预设</span>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-for="p in presets" :key="p.id" :command="p.id">
                      <span class="preset-name">{{ p.name }}</span>
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>

              <el-dropdown trigger="click" @command="setThinkingMode" v-if="currentConversation && !isMobile">
                <button class="action-btn" :class="{ active: thinkingMode !== 'auto' }">
                  <el-icon><Cpu /></el-icon>
                  <span>思维链</span>
                  <span class="mode-tag">{{ thinkingModeLabel }}</span>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="auto" :class="{ 'is-active': thinkingMode === 'auto' }">
                      <span class="option-label">自动</span>
                      <span class="option-desc">不设置</span>
                    </el-dropdown-item>
                    <el-dropdown-item command="on" :class="{ 'is-active': thinkingMode === 'on' }">
                      <span class="option-label">开启</span>
                      <span class="option-desc">强制启用</span>
                    </el-dropdown-item>
                    <el-dropdown-item command="off" :class="{ 'is-active': thinkingMode === 'off' }">
                      <span class="option-label">关闭</span>
                      <span class="option-desc">强制禁用</span>
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>

            <div class="input-hint" v-if="!isMobile">
              <span>{{ isMac ? '⌘ + Enter' : 'Ctrl + Enter' }} 发送</span>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Settings Dialog -->
    <el-dialog
      v-model="showSettingsDialog"
      title="对话设置"
      width="480px"
      class="settings-dialog"
    >
      <div class="settings-form">
        <div class="setting-item">
          <label>System Prompt</label>
          <el-input
            v-model="settingsForm.system_prompt"
            type="textarea"
            :rows="4"
            placeholder="设置系统提示词，定义 AI 的角色和行为..."
          />
        </div>

        <div class="setting-item">
          <label>
            Temperature
            <span class="setting-value">{{ settingsForm.temperature }}</span>
          </label>
          <el-slider v-model="settingsForm.temperature" :min="0" :max="2" :step="0.1" />
        </div>

        <div class="setting-item">
          <label>
            Max Tokens
            <span class="setting-value">{{ settingsForm.max_tokens }}</span>
          </label>
          <el-input-number v-model="settingsForm.max_tokens" :min="100" :max="128000" :step="100" class="w-full" />
        </div>

        <div class="setting-item">
          <label>
            Top P
            <span class="setting-value">{{ settingsForm.top_p }}</span>
          </label>
          <el-slider v-model="settingsForm.top_p" :min="0" :max="1" :step="0.05" />
        </div>
      </div>

      <template #footer>
        <el-button @click="showSettingsDialog = false">取消</el-button>
        <el-button type="primary" @click="saveSettings">保存设置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Setting, ChatLineRound, Monitor,
  Loading, Promotion, MoreFilled, Delete, MagicStick, Close, Menu, Paperclip, Operation,
  Edit, RefreshRight, DocumentCopy, Cpu
} from '@element-plus/icons-vue'
import { conversationApi, modelApi } from '@/api/conversation'
import type { Conversation, Message, ConversationSettings, PresetPrompt, ChatContentPart, ChatRequest, ChatMessage } from '@/types/conversation'
import { PRESET_PROMPTS } from '@/types/conversation'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import ThinkBlock from '@/components/chat/ThinkBlock.vue'
import ToolCallDisplay from '@/components/chat/ToolCallDisplay.vue'
import ToolsDialog from '@/components/chat/ToolsDialog.vue'
import AttachmentPreview from '@/components/chat/AttachmentPreview.vue'
import { parseMessageContent, parseStreamingThinkContent, estimateThinkTokens, removeThinkContent, parseXmlToolCalls } from '@/utils/messageParser'
import { compressImage, isImageFile, formatFileSize } from '@/utils/imageUtils'
import { useToolsStore } from '@/stores/tools'
import type { ToolCallResult, ToolCall } from '@/types/tool'

// Tools store
const toolsStore = useToolsStore()

// Throttle helper
function throttle<T extends (...args: unknown[]) => void>(fn: T, delay: number): T {
  let lastCall = 0
  return ((...args: unknown[]) => {
    const now = Date.now()
    if (now - lastCall >= delay) {
      lastCall = now
      fn(...args)
    }
  }) as T
}

// Throttled scroll to bottom (max once per 100ms)
const throttledScrollToBottom = throttle(() => {
  requestAnimationFrame(() => scrollToBottom())
}, 100)

const isAnyToolRunning = computed(() =>
  streamingToolCallResults.value.some(tc => tc.status === 'running')
)

// Visible tools (limit to 3, show count for rest)
const MAX_VISIBLE_TOOLS = 3
const visibleTools = computed(() => toolsStore.enabledTools.slice(0, MAX_VISIBLE_TOOLS))
const hiddenToolsCount = computed(() => Math.max(0, toolsStore.enabledTools.length - MAX_VISIBLE_TOOLS))

// Refs
const messagesAreaRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

// Scroll state - track if user is at bottom
const isUserAtBottom = ref(true)

// Attached files state
interface AttachedFile {
  dataUrl: string
  filename: string
  isImage: boolean
  part: { type: string; image_url?: { url: string } }
}
const attachedFiles = ref<AttachedFile[]>([])

// State
const isMobile = ref(false)
const sidebarOpen = ref(false)
const conversations = ref<Conversation[]>([])
const currentConversation = ref<Conversation | null>(null)
const messages = ref<ExtendedMessage[]>([])
const models = ref<{ name: string; alias?: string }[]>([])
const selectedModel = ref('')
const inputContent = ref('')
const sending = ref(false)
const streamingContent = ref('')
const showSettingsDialog = ref(false)
const presets = ref<PresetPrompt[]>(PRESET_PROMPTS)

// Streaming state for Think and ToolCalls
const streamingThinkContent = ref('')
const streamingToolCallResults = ref<ToolCallResult[]>([])
const showToolsDialog = ref(false)

// Track full raw content for parsing (includes think tags)
const streamingRawContent = ref('')

// Throttled streaming content for rendering (reduce CPU usage)
const throttledStreamingContent = ref('')
const throttledStreamingThink = ref('')
let throttleTimer: ReturnType<typeof setTimeout> | null = null

// Update throttled content at most every 200ms
const updateThrottledContent = () => {
  if (throttleTimer) return
  throttleTimer = setTimeout(() => {
    throttledStreamingContent.value = streamingContent.value
    throttledStreamingThink.value = streamingThinkContent.value
    throttleTimer = null
  }, 200)
}

// AbortController for stopping stream
let abortController: AbortController | null = null
let userStoppedStream = false  // Flag to track if user manually stopped

// Stop streaming and save partial content
const stopStreaming = async () => {
  if (!abortController) return

  userStoppedStream = true  // Mark as user-initiated stop
  abortController.abort()
  abortController = null

  // Save partial content if any
  if (streamingContent.value || streamingThinkContent.value) {
    const parsed = parseStreamingThinkContent(streamingRawContent.value)
    const assistantMsg: ExtendedMessage = {
      id: -Date.now(),
      conversation_id: currentConversation.value!.id,
      role: 'assistant',
      content: parsed.text,
      thinkContent: parsed.think,
      hasThink: parsed.think.length > 0,
      toolCalls: streamingToolCallResults.value.length > 0 ? streamingToolCallResults.value : undefined,
      created_at: new Date().toISOString()
    }
    messages.value.push(assistantMsg)

    // Save to history
    await saveAssistantMessage(currentConversation.value!.id, streamingRawContent.value, streamingToolCallResults.value.length > 0 ? streamingToolCallResults.value : undefined)
  }

  // Clear streaming state
  sending.value = false
  streamingRawContent.value = ''
  streamingContent.value = ''
  streamingThinkContent.value = ''
  throttledStreamingContent.value = ''
  throttledStreamingThink.value = ''
  streamingToolCallResults.value = []
  if (throttleTimer) {
    clearTimeout(throttleTimer)
    throttleTimer = null
  }
}

// Extended message type with think and tool_calls
interface ExtendedMessage extends Message {
  thinkContent?: string
  hasThink?: boolean
  toolCalls?: ToolCallResult[]
}

// Edit state
const editingBlockId = ref<string | number | null>(null)
const editingContent = ref('')
const editTextareaRef = ref<HTMLTextAreaElement | null>(null)

// Helper function to execute tool calls and send results back to AI
const executeToolCallsAndContinue = async (
  toolCalls: ToolCall[],
  _conversationId: number,
  onToolResult?: (results: ToolCallResult[]) => void
): Promise<ToolCallResult[]> => {
  const results: ToolCallResult[] = toolCalls.map(tc => ({
    id: tc.id,
    toolName: tc.function.name,
    arguments: JSON.parse(tc.function.arguments || '{}'),
    status: 'running'
  }))

  // Update UI with running status
  if (onToolResult) onToolResult(results)

  // Execute each tool
  for (let i = 0; i < results.length; i++) {
    const toolCall = results[i]
    try {
      const { executeToolCall } = await import('@/utils/toolExecutor')
      const result = await executeToolCall(toolCall.toolName, toolCall.arguments as Record<string, unknown>)
      results[i] = result
    } catch (e) {
      results[i] = {
        ...toolCall,
        status: 'error',
        error: e instanceof Error ? e.message : String(e)
      }
    }
  }

  // Update UI with final results
  if (onToolResult) onToolResult(results)

  return results
}

const settingsForm = reactive<ConversationSettings & { system_prompt: string }>({
  temperature: 0.7,
  max_tokens: 4096,
  top_p: 0.9,
  system_prompt: ''
})

// Thinking chain mode: 'auto' = not set, 'on' = force enable, 'off' = force disable
type ThinkingMode = 'auto' | 'on' | 'off'
const thinkingMode = ref<ThinkingMode>('auto')

const thinkingModeLabel = computed(() => {
  const labels: Record<ThinkingMode, string> = {
    auto: '自动',
    on: '开启',
    off: '关闭'
  }
  return labels[thinkingMode.value]
})

const setThinkingMode = (mode: ThinkingMode) => {
  thinkingMode.value = mode
}

// Get enable_thinking value for API request
const getEnableThinking = (): boolean | undefined => {
  if (thinkingMode.value === 'auto') return undefined
  return thinkingMode.value === 'on'
}

// Check mobile
const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
  if (!isMobile.value) {
    sidebarOpen.value = true
  }
}

// Check if macOS
const isMac = computed(() => {
  return navigator.platform.toUpperCase().indexOf('MAC') >= 0
})

// Auto resize textarea
const autoResize = () => {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    // Allow expansion up to 300px (about 10 lines)
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 300) + 'px'
  }
}

// Handle keydown
const handleKeydown = (e: KeyboardEvent) => {
  // 支持 Ctrl+Enter (Windows/Linux) 和 Command+Enter (macOS)
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    sendMessage()
  }
}

// Regenerate from user message
const regenerateFromUser = async (userIndex: number) => {
  if (!currentConversation.value || sending.value) return

  const userMessage = messages.value[userIndex]
  if (userMessage.role !== 'user') return

  const userContent = userMessage.content

  // Remove messages from this user message onwards (local UI update)
  messages.value = messages.value.slice(0, userIndex)

  // Re-add user message
  const tempUserMsg: ExtendedMessage = {
    id: 0,
    conversation_id: currentConversation.value.id,
    role: 'user',
    content: userContent,
    created_at: new Date().toISOString()
  }
  messages.value.push(tempUserMsg)
  isUserAtBottom.value = true

  // Delete messages after this user message in database
  try {
    await conversationApi.addMessage(currentConversation.value.id, {
      role: 'user',
      content: userContent
    })
  } catch (e) {
    console.error('Failed to save user message:', e)
  }

  // Build full messages array
  // buildChatHistory() already includes the user message we just added
  const messagesForApi = buildChatHistory()

  // Send the message
  sending.value = true
  await streamWithToolCalls(currentConversation.value.id, {
    model: selectedModel.value,
    messages: messagesForApi,
    stream: true,
    temperature: settingsForm.temperature,
    max_tokens: settingsForm.max_tokens,
    tools: toolsStore.getToolsForModel(),
    enable_thinking: getEnableThinking()
  })
}

// Start editing a text block
const startEditBlock = (blockId: string | number, block: ExpandedMessageBlock) => {
  if (block.type !== 'text') return
  editingBlockId.value = blockId
  editingContent.value = block.content
  nextTick(() => {
    const textarea = editTextareaRef.value
    if (textarea && typeof textarea.focus === 'function') {
      textarea.focus()
      textarea.style.height = 'auto'
      textarea.style.height = textarea.scrollHeight + 'px'
    }
  })
}

// Cancel editing
const cancelEdit = () => {
  editingBlockId.value = null
  editingContent.value = ''
}

// Handle keydown in edit mode
const handleEditKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    confirmEditBlock()
  } else if (e.key === 'Escape') {
    cancelEdit()
  }
}

// Confirm edit and resend
const confirmEditBlock = async () => {
  if (!editingContent.value.trim() || !currentConversation.value || editingBlockId.value === null) return

  // 找到正在编辑的块
  const block = expandedMessages.value.find(b => b.id === editingBlockId.value)
  if (!block) return

  const newTextContent = editingContent.value.trim()
  const originalIndex = block.originalIndex
  const originalMessage = messages.value[originalIndex]

  cancelEdit()

  // 检查原始消息是否包含图片
  const originalParts = parseMessageContentFromDB(originalMessage.content)
  const imageParts = originalParts.filter(p => p.type === 'image_url')

  // 构建新的消息内容
  let newContentToStore: string
  let newParts: ChatContentPart[] = []

  if (imageParts.length > 0) {
    // 有图片：保留图片，更新文本
    newParts = [...imageParts]
    if (newTextContent) {
      newParts.push({ type: 'text', text: newTextContent })
    }
    newContentToStore = JSON.stringify(newParts)
  } else {
    // 纯文本：直接更新
    newContentToStore = newTextContent
  }

  // 删除该消息之后的消息（本地）
  messages.value = messages.value.slice(0, originalIndex)

  // 添加更新后的用户消息
  const tempUserMsg: ExtendedMessage = {
    id: 0,
    conversation_id: currentConversation.value.id,
    role: 'user',
    content: newContentToStore,
    created_at: new Date().toISOString()
  }
  messages.value.push(tempUserMsg)
  isUserAtBottom.value = true

  // Save user message to database
  try {
    await conversationApi.addMessage(currentConversation.value.id, {
      role: 'user',
      content: newContentToStore
    })
  } catch (e) {
    console.error('Failed to save user message:', e)
  }

  // Build full messages array
  // buildChatHistory() already includes the user message we just added
  const messagesForApi = buildChatHistory()

  // 发送消息
  sending.value = true
  await streamWithToolCalls(currentConversation.value.id, {
    model: selectedModel.value,
    messages: messagesForApi,
    stream: true,
    temperature: settingsForm.temperature,
    max_tokens: settingsForm.max_tokens,
    tools: toolsStore.getToolsForModel(),
    enable_thinking: getEnableThinking()
  })
}

// Delete a single message (and all messages after it)
const deleteMessage = async (messageIndex: number) => {
  if (!currentConversation.value) return

  try {
    await ElMessageBox.confirm('确定删除此消息及其后续消息？', '确认删除', { type: 'warning' })

    // 本地删除消息
    messages.value = messages.value.slice(0, messageIndex)

    // TODO: 后端删除消息（需要实现专门的删除接口）
    // 当前只在前端删除，等下次发送时通过 delete_after_id 处理

    ElMessage.success('已删除')
  } catch {
    // 用户取消
  }
}

// Copy message content
const copyMessage = async (content: string) => {
  try {
    await navigator.clipboard.writeText(content)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

// Load conversations
const loadConversations = async () => {
  try {
    const response = await conversationApi.list()
    conversations.value = response.data.data || []
  } catch (error) {
    console.error('Failed to load conversations:', error)
  }
}

// Load models
const loadModels = async () => {
  try {
    const response = await modelApi.listForChat()
    models.value = response.data || []
    if (models.value.length > 0 && !selectedModel.value) {
      selectedModel.value = models.value[0].name
    }
  } catch (error) {
    console.error('Failed to load models:', error)
  }
}

// Create new conversation
const createNewConversation = async () => {
  try {
    const model = selectedModel.value || models.value[0]?.name || 'gpt-3.5-turbo'
    const response = await conversationApi.create({
      title: 'New Chat',
      model
    })
    const newConv = response.data.data
    conversations.value.unshift(newConv)
    selectConversation(newConv)
    inputContent.value = ''
    if (isMobile.value) sidebarOpen.value = false
    nextTick(() => textareaRef.value?.focus())
  } catch (error) {
    ElMessage.error('创建对话失败')
  }
}

// Select conversation
const selectConversation = async (conv: Conversation) => {
  currentConversation.value = conv
  selectedModel.value = conv.model

  // Parse settings
  if (conv.settings) {
    settingsForm.temperature = conv.settings.temperature || 0.7
    settingsForm.max_tokens = conv.settings.max_tokens || 4096
    settingsForm.top_p = conv.settings.top_p || 0.9
  }
  settingsForm.system_prompt = conv.system_prompt || ''

  // Load messages
  try {
    const response = await conversationApi.getMessages(conv.id)
    const rawMessages = response.data.data || []
    
    // Process messages to re-attach tool results
    const processedMessages: ExtendedMessage[] = []
    const toolResultsMap = new Map<string, string>() // toolName -> result content

    // First pass: collect all tool results from the conversation
    // Tool results may be saved as role: 'tool' or role: 'user' (by API when sending request)
    rawMessages.forEach((msg: Message) => {
      if (msg.role === 'tool' || (msg.role === 'user' && msg.content.startsWith('Tool: '))) {
        // Parse Tool: name\nResult: content format
        const lines = msg.content.split('\n')
        if (lines.length >= 2 && lines[0].startsWith('Tool: ')) {
          const toolName = lines[0].slice(6).trim()
          let resultPart = lines.slice(1).join('\n').trim()
          if (resultPart.startsWith('Result: ')) {
            resultPart = resultPart.slice(8).trim()
          }
          toolResultsMap.set(toolName, resultPart)
        }
      }
    })

    // Second pass: build the message list and attach results
    rawMessages.forEach((msg: Message) => {
      // Filter out tool result messages from the main list
      // Tool results may be saved as role: 'tool' or role: 'user' (by API when sending request)
      if (msg.role === 'tool' || (msg.role === 'user' && msg.content.startsWith('Tool: '))) {
        return
      }

      if (msg.role === 'assistant') {
        const parsed = parseMessageContent(msg.content)
        let toolCallsParsed: ToolCallResult[] | undefined
        
        const rawToolCallsStr = msg.tool_calls || msg.tool_calls_raw
        if (rawToolCallsStr) {
          try {
            const rawToolCalls = typeof rawToolCallsStr === 'string' ? JSON.parse(rawToolCallsStr) : rawToolCallsStr
            if (Array.isArray(rawToolCalls)) {
              toolCallsParsed = rawToolCalls.map((tc: any, idx: number) => {
                const toolName = tc.function?.name || tc.name || 'unknown'
                // Check if we have a result for this tool call in the map or in the JSON
                let result = tc.result || null
                let status = tc.status || 'success'
                let error = tc.error || null

                if (!result && toolResultsMap.has(toolName)) {
                  const rawResult = toolResultsMap.get(toolName)!
                  try {
                    result = JSON.parse(rawResult)
                  } catch {
                    result = rawResult
                  }
                }

                return {
                  id: tc.id || `tool_${idx}`,
                  toolName,
                  arguments: typeof tc.function?.arguments === 'string' ? JSON.parse(tc.function.arguments) : tc.function?.arguments || {},
                  status,
                  result,
                  error
                }
              })
            }
          } catch (e) {
            console.warn('Failed to parse tool calls:', e)
          }
        }

        processedMessages.push({
          ...msg,
          content: parsed.textContent,
          thinkContent: parsed.thinkContent,
          hasThink: parsed.hasThink,
          toolCalls: toolCallsParsed
        })
      } else {
        processedMessages.push(msg as ExtendedMessage)
      }
    })

    messages.value = processedMessages
  } catch (error) {
    console.error('Failed to load messages:', error)
    messages.value = []
  }

  // Scroll to bottom
  await nextTick()
  scrollToBottom()
  if (isMobile.value) sidebarOpen.value = false
}

// Update model
const updateModel = async () => {
  if (currentConversation.value && selectedModel.value !== currentConversation.value.model) {
    try {
      await conversationApi.update(currentConversation.value.id, { model: selectedModel.value })
      currentConversation.value.model = selectedModel.value
    } catch (error) {
      ElMessage.error('更新模型失败')
    }
  }
}

// Send message
const sendMessage = async () => {
  if ((!inputContent.value.trim() && attachedFiles.value.length === 0) || !currentConversation.value || sending.value) return

  sending.value = true
  streamingRawContent.value = ''
  streamingContent.value = ''
  streamingThinkContent.value = ''
  throttledStreamingContent.value = ''
  throttledStreamingThink.value = ''
  streamingToolCallResults.value = []
  if (throttleTimer) {
    clearTimeout(throttleTimer)
    throttleTimer = null
  }
  const content = inputContent.value.trim()
  inputContent.value = ''

  // Build parts array for multimodal content (user message)
  const parts: ChatContentPart[] = []
  if (content) {
    parts.push({ type: 'text', text: content })
  }
  for (const file of attachedFiles.value) {
    if (file.part.image_url) {
      parts.push({ type: 'image_url', image_url: file.part.image_url })
    }
  }
  // Clear attached files after building parts
  attachedFiles.value = []

  autoResize()

  // Build content to store (支持多模态格式)
  let contentToStore: string
  if (parts.length > 1 || (parts.length === 1 && parts[0].type === 'image_url')) {
    // 多模态内容：存储为 JSON 格式
    contentToStore = JSON.stringify(parts)
  } else {
    // 纯文本
    contentToStore = content
  }

  // Add user message to display immediately
  const tempUserMsg: ExtendedMessage = {
    id: 0,
    conversation_id: currentConversation.value.id,
    role: 'user',
    content: contentToStore,  // 使用多模态格式存储
    created_at: new Date().toISOString()
  }
  messages.value.push(tempUserMsg)
  // User is sending a message, force scroll to bottom
  isUserAtBottom.value = true
  scrollToBottom()

  // Save user message to database first
  try {
    await conversationApi.addMessage(currentConversation.value.id, {
      role: 'user',
      content: contentToStore
    })
  } catch (e) {
    console.error('Failed to save user message:', e)
  }

  // Build full messages array for API request
  // buildChatHistory() already includes the user message we just added to messages.value
  const messagesForApi = buildChatHistory()

  // Start the streaming loop with tool call support
  sending.value = true
  await streamWithToolCalls(currentConversation.value.id, {
    model: selectedModel.value,
    messages: messagesForApi,
    stream: true,
    temperature: settingsForm.temperature,
    max_tokens: settingsForm.max_tokens,
    tools: toolsStore.getToolsForModel(),
    enable_thinking: getEnableThinking()
  })
}

// Helper function to save assistant message to backend
const saveAssistantMessage = async (conversationId: number, content: string, toolCalls?: ToolCallResult[]) => {
  try {
    let toolCallsStr = ''
    if (toolCalls && toolCalls.length > 0) {
      // Convert to format Go backend expects, including result and error
      const formattedToolCalls = toolCalls.map(tc => ({
        id: tc.id,
        type: 'function',
        function: {
          name: tc.toolName,
          arguments: JSON.stringify(tc.arguments)
        },
        result: tc.result,
        error: tc.error,
        status: tc.status
      }))
      toolCallsStr = JSON.stringify(formattedToolCalls)
    }

    await conversationApi.addMessage(conversationId, {
      role: 'assistant',
      content: content,
      tool_calls: toolCallsStr || undefined,
      tokens: estimateThinkTokens(content) // Use the utility to estimate tokens
    })
  } catch (error) {
    console.error('Failed to save assistant message:', error)
  }
}

// Build chat history for API request (OpenAI Chat format, supports multimodal)
const buildChatHistory = (): ChatMessage[] => {
  const history: ChatMessage[] = []

  // Add system prompt if exists
  if (settingsForm.system_prompt) {
    history.push({
      role: 'system',
      content: settingsForm.system_prompt
    })
  }

  messages.value.forEach(msg => {
    // Format tool calls if they exist
    let formattedToolCalls: any[] | undefined = undefined
    if (msg.toolCalls && msg.toolCalls.length > 0) {
      formattedToolCalls = msg.toolCalls.map(tc => ({
        id: tc.id,
        type: 'function',
        function: {
          name: tc.toolName,
          arguments: JSON.stringify(tc.arguments)
        }
      }))
    }

    // 构建消息内容（支持多模态）
    let messageContent: string | ChatContentPart[]

    if (msg.role === 'assistant') {
      // Assistant 消息：纯文本（移除 think blocks）
      messageContent = removeThinkContent(msg.content)
    } else if (msg.role === 'user') {
      // User 消息：解析多模态内容
      const parts = parseMessageContentFromDB(msg.content)
      if (parts.length > 0) {
        // 多模态内容：直接使用解析后的 parts
        messageContent = parts
      } else {
        // 纯文本
        messageContent = msg.content
      }
    } else {
      // 其他角色（system, tool）：纯文本
      messageContent = msg.content
    }

    history.push({
      role: msg.role,
      content: messageContent,
      tool_calls: formattedToolCalls
    })

    // If assistant message has tool results, append them as role: 'tool' messages
    if (msg.toolCalls && msg.toolCalls.length > 0) {
      msg.toolCalls.forEach(tc => {
        if (tc.status === 'success' || tc.status === 'error') {
          history.push({
            role: 'tool',
            tool_call_id: tc.id,
            content: JSON.stringify(tc.result ?? tc.error)
          })
        }
      })
    }
  })

  return history
}

// Max iterations for tool calls to prevent infinite loops
const MAX_TOOL_ITERATIONS = 5

// Streaming loop that handles tool calls recursively
const streamWithToolCalls = async (
  conversationId: number,
  requestData: ChatRequest,
  iteration: number = 0
) => {
  // Check iteration limit
  if (iteration >= MAX_TOOL_ITERATIONS) {
    console.warn('Max tool iterations reached, stopping')
    sending.value = false
    return
  }

  // Reset streaming state
  streamingRawContent.value = ''
  streamingContent.value = ''
  streamingThinkContent.value = ''
  throttledStreamingContent.value = ''
  throttledStreamingThink.value = ''
  streamingToolCallResults.value = []
  if (throttleTimer) {
    clearTimeout(throttleTimer)
    throttleTimer = null
  }

  // Reset user stop flag and create new AbortController
  userStoppedStream = false
  abortController = new AbortController()

  // Track if tool calls were received
  let receivedToolCalls: ToolCall[] = []

  try {
    await new Promise<void>((resolve, reject) => {
      conversationApi.sendMessageStream(
        conversationId,
        requestData,
        (text) => {
          streamingRawContent.value += text
          const parsed = parseStreamingThinkContent(streamingRawContent.value)
          streamingContent.value = parsed.text
          streamingThinkContent.value = parsed.think
          updateThrottledContent()  // Throttled update for rendering
          throttledScrollToBottom()
        },
        () => {
          // Stream completed - check for XML format tool calls
          const { toolCalls: xmlToolCalls, cleanedContent } = parseXmlToolCalls(streamingRawContent.value)

          if (xmlToolCalls.length > 0) {
            // Update streaming content to remove XML tool call tags
            streamingRawContent.value = cleanedContent
            const parsed = parseStreamingThinkContent(cleanedContent)
            streamingContent.value = parsed.text
            streamingThinkContent.value = parsed.think
            throttledStreamingContent.value = parsed.text
            throttledStreamingThink.value = parsed.think

            // Process XML tool calls
            receivedToolCalls = xmlToolCalls
            streamingToolCallResults.value = xmlToolCalls.map(tc => ({
              id: tc.id,
              toolName: tc.function.name,
              arguments: JSON.parse(tc.function.arguments || '{}'),
              status: 'running'
            }))
          } else {
            // No tool calls, update throttled content immediately
            throttledStreamingContent.value = streamingContent.value
            throttledStreamingThink.value = streamingThinkContent.value
          }

          // Clear throttle timer
          if (throttleTimer) {
            clearTimeout(throttleTimer)
            throttleTimer = null
          }

          resolve()
        },
        (error) => {
          ElMessage.error(error)
          reject(new Error(error))
        },
        async (toolCalls) => {
          // Received tool calls - execute them
          receivedToolCalls = toolCalls
          streamingToolCallResults.value = toolCalls.map(tc => ({
            id: tc.id,
            toolName: tc.function.name,
            arguments: JSON.parse(tc.function.arguments || '{}'),
            status: 'running'
          }))

          // Execute tools
          const results = await executeToolCallsAndContinue(
            toolCalls,
            conversationId,
            (updatedResults) => {
              streamingToolCallResults.value = updatedResults
            }
          )

          // Check if user stopped during tool execution
          if (userStoppedStream) {
            resolve()
            return
          }

          // Save current content BEFORE clearing streaming state
          const savedRawContent = streamingRawContent.value
          const savedContent = streamingContent.value
          const savedThinkContent = streamingThinkContent.value
          const savedHasThink = streamingThinkContent.value.length > 0

          // Clear streaming state
          streamingRawContent.value = ''
          streamingContent.value = ''
          streamingThinkContent.value = ''
          throttledStreamingContent.value = ''
          throttledStreamingThink.value = ''
          streamingToolCallResults.value = []
          if (throttleTimer) {
            clearTimeout(throttleTimer)
            throttleTimer = null
          }

          // Build tool results content for saving to database
          const toolResultsContent = results.map(r =>
            `Tool: ${r.toolName}\nResult: ${JSON.stringify(r.result ?? r.error)}`
          ).join('\n\n')

          // Add assistant message to UI display FIRST
          const assistantMsg: ExtendedMessage = {
            id: -Date.now(),
            conversation_id: conversationId,
            role: 'assistant',
            content: savedContent,
            thinkContent: savedThinkContent,
            hasThink: savedHasThink,
            toolCalls: results, // results already have status: 'success'
            created_at: new Date().toISOString()
          }
          messages.value.push(assistantMsg)

          scrollToBottom()

          // NOW build messages for next request using buildChatHistory
          // buildChatHistory will automatically include the assistant message we just added
          // and will add tool results for each toolCall with status: 'success'
          const messagesForApi = buildChatHistory()

          // Save assistant message to database
          await saveAssistantMessage(conversationId, savedRawContent, results)

          // Save tool results as a tool message
          try {
            await conversationApi.addMessage(conversationId, {
              role: 'tool',
              content: toolResultsContent
            })
          } catch (e) {
            console.error('Failed to save tool results message:', e)
          }

          // Send tool results back to AI and continue streaming
          await streamWithToolCalls(
            conversationId,
            {
              model: selectedModel.value,
              messages: messagesForApi,
              stream: true,
              temperature: settingsForm.temperature,
              max_tokens: settingsForm.max_tokens,
              tools: toolsStore.getToolsForModel(),
              enable_thinking: getEnableThinking()
            },
            iteration + 1
          ).catch(console.error)
          resolve()
        },
        abortController?.signal
      )
    })

    // Finalize the message if no tool calls and user didn't stop
    if (receivedToolCalls.length === 0 && !userStoppedStream) {
      const finalRawContent = streamingRawContent.value
      const parsed = parseStreamingThinkContent(finalRawContent)

      const assistantMsg: ExtendedMessage = {
        id: -Date.now(),
        conversation_id: currentConversation.value!.id,
        role: 'assistant',
        content: parsed.text,
        thinkContent: parsed.think,
        hasThink: parsed.think.length > 0,
        toolCalls: streamingToolCallResults.value,
        created_at: new Date().toISOString()
      }
      messages.value.push(assistantMsg)

      // Save final message to history
      await saveAssistantMessage(conversationId, finalRawContent, streamingToolCallResults.value)

      // Clear streaming state AFTER adding message
      await new Promise(resolve => setTimeout(resolve, 50))
      streamingRawContent.value = ''
      streamingContent.value = ''
      streamingThinkContent.value = ''
      throttledStreamingContent.value = ''
      throttledStreamingThink.value = ''
      if (throttleTimer) {
        clearTimeout(throttleTimer)
        throttleTimer = null
      }

      // Update conversation list if needed
      if (messages.value.length <= 3) {
        loadConversations()
      }
    }

    // Handle XML format tool calls detected after stream completion
    if (receivedToolCalls.length > 0 && receivedToolCalls[0].id.startsWith('xml_tool_') && !userStoppedStream) {
      // XML format tool calls - execute them now
      const xmlToolCalls = receivedToolCalls

      // Execute tools
      const results = await executeToolCallsAndContinue(
        xmlToolCalls,
        conversationId,
        (updatedResults) => {
          streamingToolCallResults.value = updatedResults
        }
      )

      // Save current content BEFORE clearing
      const savedRawContent = streamingRawContent.value
      const savedContent = streamingContent.value
      const savedThinkContent = streamingThinkContent.value
      const savedHasThink = streamingThinkContent.value.length > 0

      // Build tool results content for saving to database
      const toolResultsContent = results.map(r =>
        `Tool: ${r.toolName}\nResult: ${JSON.stringify(r.result ?? r.error)}`
      ).join('\n\n')

      // Add assistant message to UI display FIRST
      const assistantMsg: ExtendedMessage = {
        id: -Date.now(),
        conversation_id: conversationId,
        role: 'assistant',
        content: savedContent,
        thinkContent: savedThinkContent,
        hasThink: savedHasThink,
        toolCalls: results, // results already have status: 'success'
        created_at: new Date().toISOString()
      }
      messages.value.push(assistantMsg)

      scrollToBottom()

      // NOW build messages for next request using buildChatHistory
      const messagesForApi = buildChatHistory()

      // Save assistant message to history
      await saveAssistantMessage(conversationId, savedRawContent, results)

      // Save tool result message
      try {
        await conversationApi.addMessage(conversationId, {
          role: 'tool',
          content: toolResultsContent
        })
      } catch (e) {
        console.error('Failed to save tool results message:', e)
      }

      // Clear streaming state
      streamingRawContent.value = ''
      streamingContent.value = ''
      streamingThinkContent.value = ''
      throttledStreamingContent.value = ''
      throttledStreamingThink.value = ''
      streamingToolCallResults.value = []
      if (throttleTimer) {
        clearTimeout(throttleTimer)
        throttleTimer = null
      }

      scrollToBottom()

      // Send tool results back to AI and continue streaming
      await streamWithToolCalls(
        conversationId,
        {
          model: selectedModel.value,
          messages: messagesForApi,
          stream: true,
          temperature: settingsForm.temperature,
          max_tokens: settingsForm.max_tokens,
          tools: toolsStore.getToolsForModel(),
          enable_thinking: getEnableThinking()
        },
        iteration + 1
      ).catch(console.error)
    }
  } catch (error) {
    console.error('Streaming error:', error)
  } finally {
    // Don't reset sending state if tool calls are being processed
    // (tool result continuation will handle this)
    if (receivedToolCalls.length === 0) {
      sending.value = false
    }
  }
}


// Scroll to bottom (only if user is at bottom)
const scrollToBottom = () => {
  if (messagesAreaRef.value && isUserAtBottom.value) {
    messagesAreaRef.value.scrollTop = messagesAreaRef.value.scrollHeight
  }
}

// Check if user is at bottom
const checkIsAtBottom = () => {
  if (messagesAreaRef.value) {
    const { scrollTop, scrollHeight, clientHeight } = messagesAreaRef.value
    // Consider "at bottom" if within 150px of the bottom (more tolerant)
    isUserAtBottom.value = scrollHeight - scrollTop - clientHeight < 150
  }
}

// Handle scroll event with debounce
let scrollTimeout: ReturnType<typeof setTimeout> | null = null
const handleScroll = () => {
  if (scrollTimeout) {
    clearTimeout(scrollTimeout)
  }
  scrollTimeout = setTimeout(() => {
    checkIsAtBottom()
    scrollTimeout = null
  }, 100)
}

// File upload functions
const triggerUpload = () => {
  fileInputRef.value?.click()
}

const handleFileUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement
  const files = target.files
  if (!files) return

  for (const file of Array.from(files)) {
    await addFile(file)
  }
  // Reset input
  target.value = ''
}

const handlePaste = async (e: ClipboardEvent) => {
  const items = e.clipboardData?.items
  if (!items) return

  for (const item of Array.from(items)) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) {
        await addFile(file)
      }
    }
  }
}

const addFile = async (file: File) => {
  // Check file size (max 20MB)
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.error('文件太大，最大支持20MB')
    return
  }

  const isImage = isImageFile(file)
  let dataUrl: string

  if (isImage) {
    // 对图片进行压缩处理
    try {
      const result = await compressImage(file)
      dataUrl = result.dataUrl
      // 显示压缩信息（可选）
      if (result.compressedSize < result.originalSize) {
        console.log(`图片压缩: ${formatFileSize(result.originalSize)} -> ${formatFileSize(result.compressedSize)}`)
      }
    } catch (error) {
      // 压缩失败，直接使用原图
      dataUrl = await fileToBase64(file)
    }
  } else {
    // 非图片文件直接转换
    dataUrl = await fileToBase64(file)
  }

  attachedFiles.value.push({
    dataUrl,
    filename: file.name,
    isImage,
    part: {
      type: isImage ? 'image_url' : 'text',
      image_url: isImage ? { url: dataUrl } : undefined
    }
  })
}

const fileToBase64 = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

const removeFile = (index: number) => {
  attachedFiles.value.splice(index, 1)
}

// 解析消息 Content，支持多模态格式
const parseMessageContentFromDB = (content: string): ChatContentPart[] => {
  // 尝试解析为多模态内容数组
  try {
    const parts = JSON.parse(content)
    if (Array.isArray(parts) && parts.length > 0 && parts[0].type) {
      return parts as ChatContentPart[]
    }
  } catch {
    // 不是 JSON，作为纯文本
  }
  return []
}

// 展开消息列表，让图片和文字作为单独的块显示
interface ExpandedMessageBlock {
  id: number | string          // 原始消息 ID + 后缀
  originalId: number           // 原始消息 ID
  originalIndex: number        // 原始消息在 messages 数组中的索引
  role: string
  type: 'text' | 'image'       // 块类型
  content: string              // 文本内容（type='text'）
  part?: ChatContentPart       // 图片部分（type='image'）
  message: ExtendedMessage     // 原始消息引用
}

const expandedMessages = computed<ExpandedMessageBlock[]>(() => {
  const result: ExpandedMessageBlock[] = []

  messages.value.forEach((msg, index) => {
    const parts = parseMessageContentFromDB(msg.content)

    if (parts.length > 0 && msg.role === 'user') {
      // 多模态消息：展开为多个块
      // 先显示图片块
      const imageParts = parts.filter(p => p.type === 'image_url')
      imageParts.forEach((part, partIdx) => {
        result.push({
          id: `${msg.id}-img-${partIdx}`,
          originalId: msg.id,
          originalIndex: index,
          role: msg.role,
          type: 'image',
          content: '',
          part: part,
          message: msg
        })
      })
      // 再显示文本块
      const textPart = parts.find(p => p.type === 'text')
      if (textPart?.text) {
        result.push({
          id: `${msg.id}-txt`,
          originalId: msg.id,
          originalIndex: index,
          role: msg.role,
          type: 'text',
          content: textPart.text,
          message: msg
        })
      }
    } else {
      // 纯文本消息或 assistant 消息：保持原样
      result.push({
        id: msg.id,
        originalId: msg.id,
        originalIndex: index,
        role: msg.role,
        type: 'text',
        content: msg.content,
        message: msg
      })
    }
  })

  return result
})

// Save settings
const saveSettings = async () => {
  if (!currentConversation.value) return

  try {
    await conversationApi.update(currentConversation.value.id, {
      model: selectedModel.value,
      system_prompt: settingsForm.system_prompt,
      settings: {
        temperature: settingsForm.temperature,
        max_tokens: settingsForm.max_tokens,
        top_p: settingsForm.top_p
      }
    })
    currentConversation.value.model = selectedModel.value
    currentConversation.value.system_prompt = settingsForm.system_prompt
    showSettingsDialog.value = false
    ElMessage.success('设置已保存')
  } catch (error) {
    ElMessage.error('保存失败')
  }
}

// Apply preset
const applyPreset = (presetId: string) => {
  const preset = presets.value.find(p => p.id === presetId)
  if (preset) {
    inputContent.value = preset.content
    nextTick(() => {
      textareaRef.value?.focus()
      autoResize()
    })
  }
}

// Handle conversation action
const handleConversationAction = async (action: string, conv: Conversation) => {
  if (action === 'delete') {
    try {
      await ElMessageBox.confirm('确定删除此对话？', '确认删除', { type: 'warning' })
      await conversationApi.delete(conv.id)
      conversations.value = conversations.value.filter(c => c.id !== conv.id)
      if (currentConversation.value?.id === conv.id) {
        currentConversation.value = null
        messages.value = []
      }
      ElMessage.success('已删除')
    } catch {
      // Cancelled
    }
  }
}

// Init
onMounted(() => {
  checkMobile()
  loadConversations()
  loadModels()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
  // Stop any ongoing stream when leaving the page
  if (abortController) {
    abortController.abort()
    abortController = null
  }
})
</script>

<style scoped>
.chat-page {
  display: flex;
  height: calc(100vh - 56px - 56px);
  background: #f0f2f5;
  position: relative;
}

@media (max-width: 767px) {
  .chat-page {
    height: calc(100vh - 56px - 56px - 56px);
  }
}

/* Sidebar Overlay */
.sidebar-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 99;
}

/* Sidebar */
.sidebar {
  width: 280px;
  background: #fff;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e5e7eb;
  transition: transform 0.3s ease;
  flex-shrink: 0;
}

@media (max-width: 767px) {
  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 100;
    transform: translateX(-100%);
  }

  .sidebar.open {
    transform: translateX(0);
  }
}

.sidebar-header {
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #f0f0f0;
}

.sidebar-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.sidebar-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  border-radius: 8px;
}

.sidebar-close:hover {
  background: #f3f4f6;
}

.sidebar-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 12px;
}

.new-chat-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 12px;
}

.new-chat-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 4px;
}

.conversation-item:hover {
  background: #f3f4f6;
}

.conversation-item.active {
  background: #eef2ff;
}

.conv-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f3f4f6;
  border-radius: 10px;
  color: #667eea;
  font-size: 18px;
}

.conversation-item.active .conv-icon {
  background: #e0e7ff;
}

.conv-info {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-meta {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 2px;
}

.conv-more {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  color: #9ca3af;
  opacity: 0;
  transition: all 0.2s;
}

.conversation-item:hover .conv-more {
  opacity: 1;
}

.conv-more:hover {
  background: #e5e7eb;
  color: #4b5563;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #9ca3af;
}

.empty-state p {
  margin-top: 12px;
  font-size: 14px;
}

/* Main Content */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: #f0f2f5;
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.menu-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  border-radius: 8px;
}

.menu-btn:hover {
  background: #f3f4f6;
}

.model-selector :deep(.el-select) {
  width: 180px;
}

@media (max-width: 767px) {
  .model-selector :deep(.el-select) {
    width: 140px;
  }
}

.model-selector :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px #e5e7eb;
}

.placeholder-text {
  color: #9ca3af;
  font-size: 14px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  border-radius: 8px;
}

.icon-btn:hover:not(:disabled) {
  background: #f3f4f6;
}

.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.primary-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.primary-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

@media (max-width: 767px) {
  .hide-mobile {
    display: none;
  }
}

/* Messages Area */
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.welcome-screen {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.welcome-content {
  text-align: center;
  max-width: 400px;
  padding: 20px;
}

.welcome-icon {
  width: 72px;
  height: 72px;
  margin: 0 auto 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.welcome-content h2 {
  font-size: 24px;
  font-weight: 700;
  color: #1f2937;
  margin: 0 0 8px;
}

.welcome-content p {
  font-size: 14px;
  color: #6b7280;
  margin: 0 0 24px;
}

.quick-start {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.model-select-row {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
}

.model-select-row .label {
  color: #6b7280;
  font-size: 14px;
}

.model-select-row :deep(.el-select) {
  width: 200px;
}

.start-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 28px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.start-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
}

.messages-container {
  max-width: 800px;
  margin: 0 auto;
}

/* Message Blocks */
.message-block {
  margin-bottom: 20px;
}

/* User Message */
.user-message {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.user-bubble {
  max-width: 70%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 12px 16px;
  border-radius: 18px 18px 4px 18px;
}

/* 图片块单独样式 */
.image-block {
  background: transparent;
  padding: 0;
}

.image-block :deep(.attachment-preview) {
  display: block;
}

.image-block :deep(.image-preview) {
  width: 200px;
  height: 200px;
  border-radius: 12px;
}

.user-text {
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Message Attachments */
.message-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

/* Message Actions */
.message-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.message-block:hover .message-actions {
  opacity: 1;
}

.action-icon-btn {
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

.action-icon-btn:hover {
  background: #f3f4f6;
  color: #374151;
}

.action-icon-btn.delete:hover {
  background: #fee2e2;
  color: #dc2626;
}

/* Edit Mode */
.edit-mode {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 300px;
}

.edit-textarea {
  width: 100%;
  min-height: 60px;
  padding: 10px 12px;
  border: none;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.2);
  color: white;
  font-size: 14px;
  line-height: 1.6;
  resize: none;
  outline: none;
}

.edit-textarea::placeholder {
  color: rgba(255, 255, 255, 0.6);
}

.edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.edit-btn {
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.edit-btn.cancel {
  background: rgba(255, 255, 255, 0.2);
  color: white;
}

.edit-btn.cancel:hover {
  background: rgba(255, 255, 255, 0.3);
}

.edit-btn.confirm {
  background: white;
  color: #667eea;
}

.edit-btn.confirm:hover {
  background: #f3f4f6;
}

/* Assistant Header */
.assistant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

/* Assistant Message */
.assistant-message {
  display: flex;
  gap: 12px;
}

.assistant-avatar {
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

.assistant-avatar.thinking {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
}

.assistant-content {
  flex: 1;
  min-width: 0;
}

.assistant-name {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
}

.assistant-bubble {
  background: white;
  padding: 14px 18px;
  border-radius: 4px 18px 18px 18px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  max-width: 85%;
}

.assistant-bubble.thinking {
  display: flex;
  align-items: center;
  gap: 12px;
  background: linear-gradient(135deg, #fff 0%, #fffbeb 100%);
  border: 1px solid #fef3c7;
  color: #d97706;
}

.assistant-text {
  font-size: 14px;
  line-height: 1.7;
  color: #1f2937;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Override MarkdownRenderer styles in assistant bubble */
.assistant-bubble :deep(.markdown-content) {
  font-size: 14px;
  color: #1f2937;
}

.cursor {
  display: inline-block;
  width: 2px;
  height: 15px;
  background-color: #667eea;
  margin-left: 2px;
  vertical-align: middle;
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.thinking-indicator {
  display: flex;
  gap: 4px;
}

.thinking-indicator span {
  width: 6px;
  height: 6px;
  background: #f59e0b;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.thinking-indicator span:nth-child(1) { animation-delay: -0.32s; }
.thinking-indicator span:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.thinking-text {
  font-size: 14px;
  color: #6b7280;
}

/* Tool Executing Indicator */
.tool-executing-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border-radius: 12px;
  margin-top: 8px;
  font-size: 14px;
  color: #92400e;
  font-weight: 500;
  animation: pulse-bg 1.5s ease-in-out infinite;
}

.tool-executing-indicator .el-icon {
  font-size: 18px;
  color: #d97706;
}

@keyframes pulse-bg {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* Input Area */
.input-area {
  padding: 12px 16px 16px;
  background: #fff;
  border-top: 1px solid #e5e7eb;
}

.input-container {
  max-width: 800px;
  margin: 0 auto;
}

/* Enabled Tools Bar */
.enabled-tools-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  flex-wrap: nowrap;
  overflow: hidden;
}

.tools-label {
  font-size: 12px;
  color: #6b7280;
  font-weight: 500;
  flex-shrink: 0;
}

.enabled-tools-bar :deep(.el-tag) {
  font-size: 11px;
  flex-shrink: 0;
}

.more-tools-tag {
  background: #f3f4f6;
  border-color: #e5e7eb;
  color: #6b7280;
  cursor: default;
}

/* Input Box */
.input-box {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  background: #f3f4f6;
  border-radius: 20px;
  padding: 10px 14px;
  transition: all 0.2s;
  border: 2px solid transparent;
}

.input-box:focus-within {
  border-color: #667eea;
  background: #fff;
}

.input-box.disabled {
  opacity: 0.6;
}

.upload-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: #6b7280;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.upload-btn:hover:not(:disabled) {
  background: #e5e7eb;
  color: #374151;
}

.upload-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.attached-files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 4px 0;
}

.attached-file {
  position: relative;
  display: flex;
  align-items: center;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}

.attached-file .file-preview {
  width: 48px;
  height: 48px;
  object-fit: cover;
}

.attached-file .file-name {
  padding: 4px 8px;
  font-size: 12px;
  color: #374151;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attached-file .remove-file {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ef4444;
  color: white;
  border: none;
  border-radius: 50%;
  font-size: 12px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
}

.attached-file:hover .remove-file {
  opacity: 1;
}

.input-box textarea {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  line-height: 1.5;
  color: #1f2937;
  background: transparent;
  max-height: 300px;
  min-height: 24px;
  overflow-y: auto;
  font-family: inherit;
}

.input-box textarea::placeholder {
  color: #9ca3af;
}

.input-box textarea:disabled {
  cursor: not-allowed;
}

.send-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #e5e7eb;
  color: #9ca3af;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.send-btn.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.send-btn.active:hover {
  transform: scale(1.05);
}

.send-btn:disabled {
  cursor: not-allowed;
}

.stop-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: white;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.stop-btn:hover {
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.4);
}

/* Input Footer */
.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  padding: 0 4px;
}

.input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: transparent;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #f3f4f6;
  color: #374151;
}

.action-btn.active {
  background: #eef2ff;
  color: #667eea;
}

.mode-tag {
  padding: 1px 6px;
  background: #e5e7eb;
  border-radius: 4px;
  font-size: 10px;
  color: #6b7280;
}

.action-btn.active .mode-tag {
  background: #667eea;
  color: #fff;
}

/* Dropdown menu item styles */
.option-label {
  font-weight: 500;
  color: #374151;
}

.option-desc {
  margin-left: 8px;
  font-size: 12px;
  color: #9ca3af;
}

:deep(.el-dropdown-menu__item.is-active) {
  color: #667eea;
  background-color: #f5f7ff;
}

.input-hint {
  text-align: right;
}

.input-hint span {
  font-size: 11px;
  color: #9ca3af;
}

.preset-name {
  font-weight: 500;
}

/* Settings Dialog */
.settings-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.setting-item label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 500;
  color: #374151;
  margin-bottom: 8px;
  font-size: 14px;
}

.setting-value {
  font-size: 14px;
  color: #667eea;
  font-weight: 600;
}

/* Icon button active state */
.icon-btn.active {
  background: #eef2ff;
  color: #667eea;
}
</style>