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
      <div class="messages-area" ref="messagesAreaRef">
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
            v-for="message in messages"
            :key="message.id"
            class="message-block"
            :class="message.role"
          >
            <!-- User Message -->
            <div v-if="message.role === 'user'" class="user-message">
              <div class="user-bubble">
                <div class="user-text">{{ message.content }}</div>
              </div>
            </div>

            <!-- Assistant Message -->
            <div v-else class="assistant-message">
              <div class="assistant-avatar">
                <el-icon><Monitor /></el-icon>
              </div>
              <div class="assistant-content">
                <div class="assistant-name">AI</div>
                <div class="assistant-bubble">
                  <div class="assistant-text">{{ message.content }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Streaming Message -->
          <div v-if="streamingContent" class="message-block assistant">
            <div class="assistant-message">
              <div class="assistant-avatar">
                <el-icon><Monitor /></el-icon>
              </div>
              <div class="assistant-content">
                <div class="assistant-name">AI</div>
                <div class="assistant-bubble">
                  <div class="assistant-text">
                    {{ streamingContent }}
                    <span class="cursor">▌</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Thinking State -->
          <div v-if="sending && !streamingContent" class="message-block assistant">
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
          <!-- Preset Prompts -->
          <div class="preset-bar" v-if="currentConversation && !isMobile">
            <el-dropdown trigger="click" @command="applyPreset" placement="top">
              <button class="preset-btn">
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

          <!-- Input Box -->
          <div class="input-box" :class="{ disabled: !currentConversation || sending }">
            <textarea
              ref="textareaRef"
              v-model="inputContent"
              placeholder="输入消息..."
              :disabled="!currentConversation || sending"
              @keydown="handleKeydown"
              @input="autoResize"
              rows="1"
            ></textarea>
            <button
              class="send-btn"
              :class="{ active: inputContent.trim() && currentConversation && !sending }"
              :disabled="!inputContent.trim() || !currentConversation || sending"
              @click="sendMessage"
            >
              <el-icon v-if="!sending"><Promotion /></el-icon>
              <el-icon v-else class="is-loading"><Loading /></el-icon>
            </button>
          </div>

          <div class="input-hint" v-if="!isMobile">
            <span>Ctrl + Enter 发送</span>
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
import { ref, reactive, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Setting, ChatLineRound, User, Monitor,
  Loading, Promotion, MoreFilled, Delete, MagicStick, Close, Menu
} from '@element-plus/icons-vue'
import { conversationApi, modelApi } from '@/api/conversation'
import type { Conversation, Message, ConversationSettings, PresetPrompt } from '@/types/conversation'
import { PRESET_PROMPTS } from '@/types/conversation'

// Refs
const messagesAreaRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

// State
const isMobile = ref(false)
const sidebarOpen = ref(false)
const conversations = ref<Conversation[]>([])
const currentConversation = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const models = ref<{ name: string; alias?: string }[]>([])
const selectedModel = ref('')
const inputContent = ref('')
const sending = ref(false)
const streamingContent = ref('')
const showSettingsDialog = ref(false)
const presets = ref<PresetPrompt[]>(PRESET_PROMPTS)

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

// Auto resize textarea
const autoResize = () => {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 150) + 'px'
  }
}

// Handle keydown
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && e.ctrlKey) {
    e.preventDefault()
    sendMessage()
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
    try {
      const settings = JSON.parse(conv.settings) as ConversationSettings
      settingsForm.temperature = settings.temperature || 0.7
      settingsForm.max_tokens = settings.max_tokens || 4096
      settingsForm.top_p = settings.top_p || 0.9
    } catch {
      // Use defaults
    }
  }
  settingsForm.system_prompt = conv.system_prompt || ''

  // Load messages
  try {
    const response = await conversationApi.getMessages(conv.id)
    messages.value = response.data.data || []
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
  if (!inputContent.value.trim() || !currentConversation.value || sending.value) return

  sending.value = true
  streamingContent.value = ''
  const content = inputContent.value.trim()
  inputContent.value = ''
  autoResize()

  // Add user message to display immediately
  const tempUserMsg: Message = {
    id: 0,
    conversation_id: currentConversation.value.id,
    role: 'user',
    content,
    created_at: new Date().toISOString()
  }
  messages.value.push(tempUserMsg)
  scrollToBottom()

  try {
    await conversationApi.sendMessageStream(
      currentConversation.value.id,
      { content, stream: true, settings: { temperature: settingsForm.temperature, max_tokens: settingsForm.max_tokens } },
      (text) => {
        streamingContent.value += text
        scrollToBottom()
      },
      async () => {
        sending.value = false
        streamingContent.value = ''
        try {
          const response = await conversationApi.getMessages(currentConversation.value!.id)
          messages.value = response.data.data || []
          if (messages.value.length === 2) {
            loadConversations()
          }
        } catch {
          // Keep current messages
        }
        scrollToBottom()
      },
      (error) => {
        sending.value = false
        streamingContent.value = ''
        ElMessage.error(error)
        messages.value = messages.value.filter(m => m.id !== 0)
      }
    )
  } catch (error) {
    sending.value = false
    streamingContent.value = ''
    ElMessage.error('发送失败')
  }
}

// Scroll to bottom
const scrollToBottom = () => {
  if (messagesAreaRef.value) {
    messagesAreaRef.value.scrollTop = messagesAreaRef.value.scrollHeight
  }
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
  justify-content: flex-end;
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
  margin-bottom: 6px;
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
}

.assistant-text {
  font-size: 14px;
  line-height: 1.7;
  color: #1f2937;
  white-space: pre-wrap;
  word-break: break-word;
}

.cursor {
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.thinking-indicator {
  display: flex;
  gap: 4px;
}

.thinking-indicator span {
  width: 8px;
  height: 8px;
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

.preset-bar {
  margin-bottom: 10px;
}

.preset-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #f3f4f6;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s;
}

.preset-btn:hover {
  background: #e5e7eb;
}

.preset-name {
  font-weight: 500;
}

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

.input-hint {
  text-align: center;
  margin-top: 8px;
}

.input-hint span {
  font-size: 12px;
  color: #9ca3af;
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
</style>