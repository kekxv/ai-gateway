<template>
  <div class="chat-page">
    <!-- Sidebar - Conversation List -->
    <aside class="sidebar" :class="{ collapsed: !sidebarOpen }">
      <div class="sidebar-header">
        <div class="sidebar-toggle" @click="sidebarOpen = !sidebarOpen">
          <el-icon><Fold v-if="sidebarOpen" /><Expand v-else /></el-icon>
        </div>
        <span v-if="sidebarOpen" class="sidebar-title">对话历史</span>
      </div>

      <div class="sidebar-content" v-show="sidebarOpen">
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
            <el-icon class="conv-icon"><ChatLineRound /></el-icon>
            <div class="conv-info">
              <div class="conv-title">{{ conv.title }}</div>
              <div class="conv-meta">{{ conv.model }} · {{ formatDateShort(conv.updated_at) }}</div>
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
          <button v-if="!sidebarOpen" class="toggle-btn" @click="sidebarOpen = true">
            <el-icon><Expand /></el-icon>
          </button>

          <!-- Model Selector -->
          <div class="model-selector" v-if="currentConversation">
            <el-select
              v-model="selectedModel"
              placeholder="选择模型"
              size="large"
              @change="updateModel"
            >
              <el-option
                v-for="model in models"
                :key="model.name"
                :label="model.name"
                :value="model.name"
              >
                <div class="model-option">
                  <span class="model-name">{{ model.name }}</span>
                  <span class="model-alias" v-if="model.alias">{{ model.alias }}</span>
                </div>
              </el-option>
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
            <span>新对话</span>
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

            <div class="quick-actions">
              <div class="quick-action" @click="createNewConversation">
                <el-icon><ChatLineRound /></el-icon>
                <span>开始新对话</span>
              </div>
            </div>

            <!-- Model Selection for New Chat -->
            <div class="new-chat-model-select">
              <span class="label">选择模型：</span>
              <el-select
                v-model="selectedModel"
                placeholder="选择模型"
                size="large"
              >
                <el-option
                  v-for="model in models"
                  :key="model.name"
                  :label="model.name"
                  :value="model.name"
                />
              </el-select>
            </div>
          </div>
        </div>

        <!-- Messages -->
        <div v-else class="messages-container">
          <div
            v-for="message in messages"
            :key="message.id"
            class="message-row"
            :class="message.role"
          >
            <div class="message-content">
              <div class="message-avatar" :class="message.role">
                <el-icon v-if="message.role === 'user'"><User /></el-icon>
                <el-icon v-else><Monitor /></el-icon>
              </div>
              <div class="message-body">
                <div class="message-role">{{ message.role === 'user' ? '你' : 'AI' }}</div>
                <div class="message-text">{{ message.content }}</div>
              </div>
            </div>
          </div>

          <!-- Streaming Message -->
          <div v-if="streamingContent" class="message-row assistant streaming">
            <div class="message-content">
              <div class="message-avatar assistant">
                <el-icon><Monitor /></el-icon>
              </div>
              <div class="message-body">
                <div class="message-role">AI</div>
                <div class="message-text">
                  {{ streamingContent }}
                  <span class="cursor">▌</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="sending && !streamingContent" class="message-row assistant loading">
            <div class="message-content">
              <div class="message-avatar assistant">
                <el-icon><Monitor /></el-icon>
              </div>
              <div class="message-body">
                <div class="message-role">AI</div>
                <div class="message-text loading-dots">
                  <span></span><span></span><span></span>
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
          <div class="preset-bar" v-if="currentConversation">
            <el-dropdown trigger="click" @command="applyPreset" placement="top">
              <button class="preset-btn">
                <el-icon><MagicStick /></el-icon>
                <span>预设 Prompt</span>
                <el-icon class="arrow"><ArrowDown /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="p in presets"
                    :key="p.id"
                    :command="p.id"
                  >
                    <div class="preset-item">
                      <span class="preset-name">{{ p.name }}</span>
                      <span class="preset-desc">{{ p.description }}</span>
                    </div>
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
              :disabled="!inputContent.trim() || !currentConversation || sending"
              @click="sendMessage"
            >
              <el-icon v-if="!sending"><Promotion /></el-icon>
              <el-icon v-else class="is-loading"><Loading /></el-icon>
            </button>
          </div>

          <div class="input-hint">
            <span>按 Ctrl + Enter 发送</span>
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
          <p class="setting-hint">较低值更确定，较高值更有创意</p>
        </div>

        <div class="setting-item">
          <label>
            Max Tokens
            <span class="setting-value">{{ settingsForm.max_tokens }}</span>
          </label>
          <el-input-number v-model="settingsForm.max_tokens" :min="100" :max="128000" :step="100" class="w-full" />
          <p class="setting-hint">响应的最大 token 数量</p>
        </div>

        <div class="setting-item">
          <label>
            Top P
            <span class="setting-value">{{ settingsForm.top_p }}</span>
          </label>
          <el-slider v-model="settingsForm.top_p" :min="0" :max="1" :step="0.05" />
          <p class="setting-hint">核采样参数，控制输出多样性</p>
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
import { ref, reactive, onMounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Fold, Expand, Plus, Setting, ChatLineRound, User, Monitor,
  Loading, Promotion, MoreFilled, Delete, MagicStick, ArrowDown
} from '@element-plus/icons-vue'
import { conversationApi, modelApi } from '@/api/conversation'
import type { Conversation, Message, ConversationSettings, PresetPrompt } from '@/types/conversation'
import { PRESET_PROMPTS } from '@/types/conversation'
import dayjs from 'dayjs'

// Refs
const messagesAreaRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

// State
const sidebarOpen = ref(true)
const conversations = ref<Conversation[]>([])
const currentConversation = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const models = ref<{ name: string; alias?: string }[]>([])
const selectedModel = ref('')
const inputContent = ref('')
const sending = ref(false)
const streamingContent = ref('')
const showSettingsDialog = ref(false)
const selectedPreset = ref('')
const presets = ref<PresetPrompt[]>(PRESET_PROMPTS)

const settingsForm = reactive<ConversationSettings & { system_prompt: string }>({
  temperature: 0.7,
  max_tokens: 4096,
  top_p: 0.9,
  system_prompt: ''
})

// Helper functions
const formatDateShort = (date: string) => {
  const d = dayjs(date)
  const now = dayjs()
  if (d.isSame(now, 'day')) return d.format('HH:mm')
  if (d.isSame(now, 'year')) return d.format('MM-DD')
  return d.format('YYYY-MM-DD')
}

// Auto resize textarea
const autoResize = () => {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 200) + 'px'
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
          // Update conversation title if first message
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
    showSettingsDialog = false
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
  loadConversations()
  loadModels()
})
</script>

<style scoped>
.chat-page {
  display: flex;
  height: calc(100vh - 56px - 56px);
  background: #f8fafc;
}

@media (max-width: 768px) {
  .chat-page {
    height: calc(100vh - 56px - 56px - 56px);
  }
}

/* Sidebar */
.sidebar {
  width: 280px;
  background: white;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
}

.sidebar.collapsed {
  width: 56px;
}

.sidebar-header {
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid #e2e8f0;
}

.sidebar-toggle {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  cursor: pointer;
  color: #64748b;
  transition: all 0.2s;
}

.sidebar-toggle:hover {
  background: #f1f5f9;
  color: #334155;
}

.sidebar-title {
  font-weight: 600;
  color: #1e293b;
  font-size: 15px;
}

.sidebar-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.new-chat-btn {
  margin: 12px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.new-chat-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
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
  background: #f1f5f9;
}

.conversation-item.active {
  background: #eef2ff;
}

.conv-icon {
  color: #6366f1;
  font-size: 20px;
}

.conv-info {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-size: 14px;
  font-weight: 500;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-meta {
  font-size: 12px;
  color: #94a3b8;
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
  color: #94a3b8;
  opacity: 0;
  transition: all 0.2s;
}

.conversation-item:hover .conv-more {
  opacity: 1;
}

.conv-more:hover {
  background: #e2e8f0;
  color: #475569;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #94a3b8;
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
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background: white;
  border-bottom: 1px solid #e2e8f0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.toggle-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e2e8f0;
  background: white;
  border-radius: 10px;
  cursor: pointer;
  color: #64748b;
  transition: all 0.2s;
}

.toggle-btn:hover {
  background: #f8fafc;
  color: #334155;
}

.model-selector :deep(.el-select) {
  width: 220px;
}

.model-selector :deep(.el-input__wrapper) {
  border-radius: 10px;
  box-shadow: 0 0 0 1px #e2e8f0;
}

.model-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-name {
  font-weight: 500;
}

.model-alias {
  font-size: 12px;
  color: #94a3b8;
}

.placeholder-text {
  color: #94a3b8;
  font-size: 15px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.icon-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e2e8f0;
  background: white;
  border-radius: 10px;
  cursor: pointer;
  color: #64748b;
  transition: all 0.2s;
}

.icon-btn:hover:not(:disabled) {
  background: #f8fafc;
  color: #334155;
}

.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.primary-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.primary-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
}

/* Messages Area */
.messages-area {
  flex: 1;
  overflow-y: auto;
}

.welcome-screen {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.welcome-content {
  text-align: center;
  max-width: 480px;
}

.welcome-icon {
  width: 80px;
  height: 80px;
  margin: 0 auto 24px;
  background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6366f1;
}

.welcome-content h2 {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 8px;
}

.welcome-content p {
  font-size: 16px;
  color: #64748b;
  margin: 0 0 32px;
}

.quick-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-bottom: 32px;
}

.quick-action {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 24px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s;
  color: #334155;
  font-weight: 500;
}

.quick-action:hover {
  border-color: #6366f1;
  background: #f8fafc;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.new-chat-model-select {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.new-chat-model-select .label {
  color: #64748b;
  font-size: 14px;
}

.messages-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}

.message-row {
  margin-bottom: 24px;
}

.message-content {
  display: flex;
  gap: 16px;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: white;
}

.message-avatar.user {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
}

.message-avatar.assistant {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
}

.message-body {
  flex: 1;
  min-width: 0;
}

.message-role {
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 6px;
}

.message-text {
  font-size: 15px;
  line-height: 1.7;
  color: #1e293b;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-row.user .message-text {
  background: #f1f5f9;
  padding: 16px 20px;
  border-radius: 16px;
  border-top-left-radius: 4px;
}

.cursor {
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.loading-dots {
  display: flex;
  gap: 4px;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  background: #94a3b8;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dots span:nth-child(1) { animation-delay: -0.32s; }
.loading-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* Input Area */
.input-area {
  padding: 16px 24px 24px;
  background: linear-gradient(to top, white 0%, rgba(255, 255, 255, 0.9) 100%);
}

.input-container {
  max-width: 800px;
  margin: 0 auto;
}

.preset-bar {
  margin-bottom: 12px;
}

.preset-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
}

.preset-btn:hover {
  background: #f1f5f9;
  color: #334155;
}

.preset-btn .arrow {
  font-size: 12px;
}

.preset-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.preset-name {
  font-weight: 500;
}

.preset-desc {
  font-size: 12px;
  color: #94a3b8;
}

.input-box {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 12px 16px;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.input-box:focus-within {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.input-box.disabled {
  background: #f8fafc;
}

.input-box textarea {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  font-size: 15px;
  line-height: 1.5;
  color: #1e293b;
  background: transparent;
  max-height: 200px;
}

.input-box textarea::placeholder {
  color: #94a3b8;
}

.input-box textarea:disabled {
  cursor: not-allowed;
}

.send-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  transform: scale(1.05);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-hint {
  text-align: center;
  margin-top: 8px;
}

.input-hint span {
  font-size: 12px;
  color: #94a3b8;
}

/* Settings Dialog */
.settings-dialog .settings-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.setting-item label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 500;
  color: #334155;
  margin-bottom: 8px;
}

.setting-value {
  font-size: 14px;
  color: #6366f1;
  font-weight: 600;
}

.setting-hint {
  font-size: 12px;
  color: #94a3b8;
  margin: 4px 0 0;
}
</style>