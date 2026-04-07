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
      <!-- Tools Panel -->
      <ToolPanel :is-open="showToolsPanel" @close="showToolsPanel = false" />

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
          <button class="icon-btn" @click="showToolsPanel = !showToolsPanel" :class="{ active: showToolsPanel }" title="工具">
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
            v-for="(message, index) in messages"
            :key="message.id"
            class="message-block"
            :class="message.role"
          >
            <!-- User Message -->
            <div v-if="message.role === 'user'" class="user-message">
              <div class="user-bubble">
                <div v-if="editingMessageIndex === index" class="edit-mode">
                  <textarea
                    ref="editTextareaRef"
                    v-model="editingContent"
                    class="edit-textarea"
                    rows="2"
                    @keydown="handleEditKeydown($event, index)"
                  ></textarea>
                  <div class="edit-actions">
                    <button class="edit-btn cancel" @click="cancelEdit">取消</button>
                    <button class="edit-btn confirm" @click="confirmEdit(index)">发送</button>
                  </div>
                </div>
                <div v-else class="user-text">{{ message.content }}</div>
              </div>
              <div v-if="editingMessageIndex !== index && !sending" class="message-actions">
                <button class="action-icon-btn" @click="startEdit(index)" title="编辑">
                  <el-icon><Edit /></el-icon>
                </button>
                <button class="action-icon-btn" @click="regenerateFromUser(index)" title="重新生成">
                  <el-icon><RefreshRight /></el-icon>
                </button>
              </div>
            </div>

            <!-- Assistant Message (exclude tool role messages) -->
            <div v-else-if="message.role !== 'tool'" class="assistant-message">
              <div class="assistant-avatar">
                <el-icon><Monitor /></el-icon>
              </div>
              <div class="assistant-content">
                <div class="assistant-header">
                  <div class="assistant-name">AI</div>
                  <div v-if="!sending" class="message-actions">
                    <button class="action-icon-btn" @click="copyMessage(message.content)" title="复制">
                      <el-icon><DocumentCopy /></el-icon>
                    </button>
                  </div>
                </div>
                <!-- Think Block -->
                <ThinkBlock
                  v-if="message.hasThink"
                  :content="message.thinkContent || ''"
                  :tokens="estimateThinkTokens(message.thinkContent || '')"
                  :default-collapsed="true"
                  :force-expand="!message.content && (!message.toolCalls || message.toolCalls.length === 0)"
                />
                <!-- Tool Calls Display -->
                <ToolCallDisplay
                  v-if="message.toolCalls && message.toolCalls.length > 0"
                  :tool-calls="message.toolCalls"
                />
                <!-- Markdown Content -->
                <div v-if="message.content" class="assistant-bubble">
                  <MarkdownRenderer :content="message.content" />
                </div>
              </div>
            </div>
          </div>

          <!-- Streaming Message -->
          <div v-if="streamingContent || streamingThinkContent || streamingToolCallResults.length > 0" class="message-block assistant">
            <div class="assistant-message">
              <div class="assistant-avatar">
                <el-icon><Monitor /></el-icon>
              </div>
              <div class="assistant-content">
                <div class="assistant-name">AI</div>
                <!-- Streaming Think Block -->
                <ThinkBlock
                  v-if="streamingThinkContent"
                  :content="streamingThinkContent"
                  :default-collapsed="true"
                  :force-expand="!streamingContent && streamingToolCallResults.length === 0"
                />
                <!-- Streaming Tool Calls Display -->
                <ToolCallDisplay
                  v-if="streamingToolCallResults.length > 0"
                  :tool-calls="streamingToolCallResults"
                />
                <!-- Streaming Markdown Content -->
                <div v-if="streamingContent" class="assistant-bubble">
                  <MarkdownRenderer :content="streamingContent" />
                  <span class="cursor" v-if="sending">▌</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Thinking State - only show when no streaming content yet -->
          <div v-if="sending && !streamingContent && !streamingThinkContent" class="message-block assistant">
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
              v-for="tool in toolsStore.enabledTools"
              :key="tool.id"
              size="small"
              closable
              @close="toolsStore.toggleTool(tool.id)"
            >
              {{ tool.name }}
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
            <button
              class="send-btn"
              :class="{ active: (inputContent.trim() || attachedFiles.length > 0) && currentConversation && !sending }"
              :disabled="(!inputContent.trim() && attachedFiles.length === 0) || !currentConversation || sending"
              @click="sendMessage"
            >
              <el-icon v-if="!sending"><Promotion /></el-icon>
              <el-icon v-else class="is-loading"><Loading /></el-icon>
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
  Edit, RefreshRight, DocumentCopy
} from '@element-plus/icons-vue'
import { conversationApi, modelApi } from '@/api/conversation'
import type { Conversation, Message, ConversationSettings, PresetPrompt, ChatContentPart, ChatRequest } from '@/types/conversation'
import { PRESET_PROMPTS } from '@/types/conversation'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import ThinkBlock from '@/components/chat/ThinkBlock.vue'
import ToolCallDisplay from '@/components/chat/ToolCallDisplay.vue'
import ToolPanel from '@/components/chat/ToolPanel.vue'
import { parseMessageContent, parseStreamingThinkContent, estimateThinkTokens } from '@/utils/messageParser'
import { useToolsStore } from '@/stores/tools'
import type { ToolCallResult, ToolCall } from '@/types/tool'

// Tools store
const toolsStore = useToolsStore()

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
const showToolsPanel = ref(false)

// Track full raw content for parsing (includes think tags)
const streamingRawContent = ref('')

// Edit state
const editingMessageIndex = ref<number | null>(null)
const editingContent = ref('')
const editTextareaRef = ref<HTMLTextAreaElement | null>(null)

// Extended message type with think and tool_calls
interface ExtendedMessage extends Message {
  thinkContent?: string
  hasThink?: boolean
  toolCalls?: ToolCallResult[]
}

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
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 150) + 'px'
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

// Start editing a message
const startEdit = (index: number) => {
  const message = messages.value[index]
  if (message.role !== 'user') return
  editingMessageIndex.value = index
  editingContent.value = message.content
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
  editingMessageIndex.value = null
  editingContent.value = ''
}

// Handle keydown in edit mode
const handleEditKeydown = (e: KeyboardEvent, index: number) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    confirmEdit(index)
  } else if (e.key === 'Escape') {
    cancelEdit()
  }
}

// Confirm edit and resend
const confirmEdit = async (index: number) => {
  if (!editingContent.value.trim() || !currentConversation.value) return

  const newContent = editingContent.value.trim()
  // Get the message ID before this index (for delete_after_id)
  // When index=0 (first message), prevMessageId=0, which will delete all messages (id > 0)
  const prevMessageId = index > 0 ? messages.value[index - 1].id : 0
  cancelEdit()

  // Remove all messages from this index onwards (local UI update)
  const messagesBeforeEdit = messages.value.slice(0, index)
  messages.value = messagesBeforeEdit

  // Add the new user message locally
  const tempUserMsg: ExtendedMessage = {
    id: 0,
    conversation_id: currentConversation.value.id,
    role: 'user',
    content: newContent,
    created_at: new Date().toISOString()
  }
  messages.value.push(tempUserMsg)
  isUserAtBottom.value = true

  // Send the message
  sending.value = true
  await streamWithToolCalls(currentConversation.value.id, {
    content: newContent,
    stream: true,
    settings: {
      temperature: settingsForm.temperature,
      max_tokens: settingsForm.max_tokens
    },
    tools: toolsStore.getToolsForModel(),
    delete_after_id: prevMessageId
  })
}

// Regenerate from user message
const regenerateFromUser = async (userIndex: number) => {
  if (!currentConversation.value || sending.value) return

  const userMessage = messages.value[userIndex]
  if (userMessage.role !== 'user') return

  const userContent = userMessage.content

  // Get the message ID before this user message (for delete_after_id)
  // We need to delete messages AFTER the previous message, which includes the current user message
  // When userIndex=0 (first message), prevMessageId=0, which will delete all messages (id > 0)
  const prevMessageId = userIndex > 0 ? messages.value[userIndex - 1].id : 0

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

  // Send the message
  sending.value = true
  await streamWithToolCalls(currentConversation.value.id, {
    content: userContent,
    stream: true,
    settings: {
      temperature: settingsForm.temperature,
      max_tokens: settingsForm.max_tokens
    },
    tools: toolsStore.getToolsForModel(),
    delete_after_id: prevMessageId
  })
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
    rawMessages.forEach((msg: Message) => {
      if (msg.role === 'tool' || (msg.role === 'user' && typeof msg.content === 'string' && msg.content.startsWith('Tool: '))) {
        // Parse Tool: name\nResult: content
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
      if (msg.role === 'tool' || (msg.role === 'user' && typeof msg.content === 'string' && msg.content.startsWith('Tool: '))) {
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
                // Check if we have a result for this tool call in the map (from pass 1) or in the JSON (from saveAssistantMessage)
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
  streamingToolCallResults.value = []
  const content = inputContent.value.trim()
  inputContent.value = ''

  // Build parts array for multimodal content
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

  // Add user message to display immediately
  const tempUserMsg: ExtendedMessage = {
    id: 0,
    conversation_id: currentConversation.value.id,
    role: 'user',
    content,
    created_at: new Date().toISOString()
  }
  messages.value.push(tempUserMsg)
  // User is sending a message, force scroll to bottom
  isUserAtBottom.value = true
  scrollToBottom()

  // Start the streaming loop with tool call support
  sending.value = true
  await streamWithToolCalls(currentConversation.value.id, { content, parts, stream: true, settings: {
    temperature: settingsForm.temperature,
    max_tokens: settingsForm.max_tokens
  }, tools: toolsStore.getToolsForModel() })
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

// Streaming loop that handles tool calls recursively
const streamWithToolCalls = async (
  conversationId: number,
  requestData: ChatRequest,
  isToolResultRequest: boolean = false
) => {
  // Reset streaming state
  streamingRawContent.value = ''
  streamingContent.value = ''
  streamingThinkContent.value = ''
  streamingToolCallResults.value = []

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
          scrollToBottom()
        },
        () => {
          // Stream completed
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

          // Build tool results message to send back to AI
          const toolResultsContent = results.map(r =>
            `Tool: ${r.toolName}\nResult: ${JSON.stringify(r.result ?? r.error)}`
          ).join('\n\n')

          // Add assistant message with tool calls to display
          const assistantMsg: ExtendedMessage = {
            id: -Date.now(),
            conversation_id: conversationId,
            role: 'assistant',
            content: streamingContent.value,
            thinkContent: streamingThinkContent.value,
            hasThink: streamingThinkContent.value.length > 0,
            toolCalls: results,
            created_at: new Date().toISOString()
          }
          messages.value.push(assistantMsg)

          // Save this intermediate state to history
          await saveAssistantMessage(conversationId, streamingRawContent.value, results)

          // Also save the "tool result" message that we're about to send
          try {
            await conversationApi.addMessage(conversationId, {
              role: 'tool',
              content: toolResultsContent
            })
          } catch (e) {
            console.error('Failed to save tool results message:', e)
          }

          // Clear streaming state (but keep toolCallResults in the message)
          streamingRawContent.value = ''
          streamingContent.value = ''
          streamingThinkContent.value = ''
          streamingToolCallResults.value = []

          scrollToBottom()

          // Send tool results back to AI and continue streaming
          // Await this to keep sending.value = true until the end
          await streamWithToolCalls(
            conversationId,
            {
              content: toolResultsContent,
              stream: true,
              settings: {
                temperature: settingsForm.temperature,
                max_tokens: settingsForm.max_tokens
              },
              tools: toolsStore.getToolsForModel()
            },
            true
          ).catch(console.error)
          resolve()
        }
      )
    })

    // If this wasn't a tool result request, finalize the message
    if (!isToolResultRequest && receivedToolCalls.length === 0) {
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

      // Update conversation list if needed
      if (messages.value.length <= 3) {
        loadConversations()
      }
    } else if (isToolResultRequest && receivedToolCalls.length === 0) {
      // Tool result request completed - save the final AI response
      const finalRawContent = streamingRawContent.value
      const parsed = parseStreamingThinkContent(finalRawContent)

      const finalContent = streamingContent.value || parsed.text
      const finalThink = streamingThinkContent.value || parsed.think

      // Save final response to history
      await saveAssistantMessage(conversationId, finalRawContent)

      // Add new assistant message for AI's response
      messages.value.push({
        id: -Date.now(),
        conversation_id: conversationId,
        role: 'assistant',
        content: finalContent,
        thinkContent: finalThink,
        hasThink: finalThink.length > 0,
        created_at: new Date().toISOString()
      })

      // Clear streaming state
      streamingRawContent.value = ''
      streamingContent.value = ''
      streamingThinkContent.value = ''

      if (messages.value.length <= 3) {
        loadConversations()
      }

      scrollToBottom()
    }
  } catch (error) {
    console.error('Streaming error:', error)
  } finally {
    if (!isToolResultRequest) {
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

  const isImage = file.type.startsWith('image/')
  const dataUrl = await fileToBase64(file)

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

.user-text {
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
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
  flex-wrap: wrap;
}

.tools-label {
  font-size: 12px;
  color: #6b7280;
  font-weight: 500;
}

.enabled-tools-bar :deep(.el-tag) {
  font-size: 11px;
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
  max-height: 150px;
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