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
        <div class="new-chat-buttons">
          <button class="new-chat-btn" @click="createNewConversation(false)">
            <el-icon><Plus /></el-icon>
            <span>新对话</span>
          </button>
          <button class="temp-chat-btn" @click="createNewConversation(true)" title="临时对话不会保存到数据库">
            <el-icon><Timer /></el-icon>
            <span>临时</span>
          </button>
        </div>

        <!-- Show temporary conversation indicator -->
        <div v-if="isTemporaryConversation && currentConversation" class="temporary-indicator">
          <el-icon><Timer /></el-icon>
          <span>临时对话</span>
          <span class="temp-hint">（不保存）</span>
        </div>

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
              <div class="conv-meta">
                <span class="conv-model">{{ conv.model }}</span>
              </div>
            </div>
            <el-dropdown trigger="click" @command="handleConversationAction($event, conv)">
              <button class="conv-more" @click.stop>
                <el-icon><MoreFilled /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename">
                    <el-icon><Edit /></el-icon>
                    重命名
                  </el-dropdown-item>
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

          <div class="title-panel" v-if="currentConversation">
            <div class="title-copy">
              <div class="eyebrow">会话工作台</div>
              <div class="conversation-name">{{ currentConversation.title }}</div>
            </div>
            <div class="selector-cluster">
              <div class="model-selector">
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
            </div>
          </div>
          <div class="model-selector" v-else>
            <span class="placeholder-text">选择模型后开始新的会话</span>
          </div>
        </div>

        <div class="header-right">
          <!-- Skills & Tools row -->
          <div class="header-tools-row">
            <!-- Skills Dropdown -->
            <el-dropdown trigger="click" @command="activateSkill" placement="bottom-end" :disabled="!currentConversation || skillsStore.enabledSkills.length === 0">
              <button class="icon-btn" :class="{ active: activeSkillName }" title="技能">
                <el-icon><Collection /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="activeSkillName" command="">
                    <div class="skill-option">
                      <span class="skill-name text-warning">取消当前技能</span>
                    </div>
                  </el-dropdown-item>
                  <el-dropdown-item divided v-for="skill in skillsStore.enabledSkills" :key="skill.id" :command="skill.name">
                    <div class="skill-option">
                      <span class="skill-name">{{ skill.display_name || skill.name }}</span>
                      <span class="skill-desc">{{ skill.description }}</span>
                    </div>
                  </el-dropdown-item>
                  <el-dropdown-item v-if="skillsStore.enabledSkills.length === 0" disabled>
                    <span class="text-gray-400">暂无可用技能</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <!-- Tools Button -->
            <button class="icon-btn" @click="showToolSelector = true" title="工具">
              <el-icon><Operation /></el-icon>
            </button>
          </div>
          <button class="icon-btn" @click="showSettingsDialog = true" :disabled="!currentConversation" title="设置">
            <el-icon><Setting /></el-icon>
          </button>
          <button class="primary-btn" @click="createNewConversation(false)">
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
            <div class="welcome-hero">
              <div class="welcome-icon">
                <el-icon :size="48"><Promotion /></el-icon>
              </div>
              <div class="hero-copy">
                <span class="hero-kicker">AI Gateway Chat</span>
                <h2>统一聊天入口，按模型自动切换协议</h2>
                <p>支持多种模型，自动适配协议。选择模型后开始对话。</p>
              </div>
            </div>

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
              <div class="welcome-model-meta">
                <div class="welcome-model-card">
                  <span class="meta-label">当前模型</span>
                  <strong>{{ currentModelLabel }}</strong>
                </div>
              </div>
              <div class="feature-grid">
                <div class="feature-card">
                  <span class="feature-title">智能对话</span>
                  <span class="feature-desc">支持多种 AI 模型，自动适配最佳协议进行对话。</span>
                </div>
                <div class="feature-card">
                  <span class="feature-title">多模态输入</span>
                  <span class="feature-desc">继续支持图片粘贴、文件上传、工具与技能联动。</span>
                </div>
              </div>
              <div class="start-buttons">
                <button class="start-btn" @click="createNewConversation(false)">
                  <el-icon><ChatLineRound /></el-icon>
                  <span>开始对话</span>
                </button>
                <button class="start-btn temp" @click="createNewConversation(true)" title="临时对话不保存到数据库">
                  <el-icon><Timer /></el-icon>
                  <span>临时对话</span>
                </button>
              </div>
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
                  <!-- 文本块 - 使用 Markdown 渲染 -->
                  <div v-else class="user-text">
                    <MarkdownRenderer :content="block.content" />
                  </div>
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
                <!-- Error Message -->
                <div v-if="block.message.hasError" class="error-bubble">
                  <el-icon class="error-icon"><WarningFilled /></el-icon>
                  <span class="error-text">{{ block.message.error }}</span>
                  <button class="retry-btn" @click="retryLastMessage" title="重试">
                    <el-icon><RefreshRight /></el-icon>
                    重试
                  </button>
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
                  :request-messages="getRequestMessagesForBlock(block)"
                />
                <!-- Markdown Content -->
                <div v-if="block.message.content" class="assistant-bubble">
                  <MarkdownRenderer :content="block.message.content" />
                </div>
              </div>
            </div>
          </div>

          <!-- Streaming Message -->
          <div v-if="throttledStreamingContent.trim() || throttledStreamingThink || streamingToolCallResults.length > 0" class="message-block assistant">
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
                  :force-expand="!throttledStreamingContent.trim() && streamingToolCallResults.length === 0"
                />
                <!-- Streaming Tool Calls Display -->
                <ToolCallDisplay
                  v-if="streamingToolCallResults.length > 0"
                  :tool-calls="streamingToolCallResults"
                  :request-messages="messages.map(m => ({ role: m.role, content: m.content }))"
                />

                <!-- Tool Executing Indicator - show when tools are running and no result yet -->
                <div v-if="isAnyToolRunning" class="tool-executing-indicator">
                  <el-icon class="is-loading"><Loading /></el-icon>
                  <span>正在执行工具...</span>
                </div>

                <!-- Streaming Markdown Content -->
                <div v-if="throttledStreamingContent.trim()" class="assistant-bubble">
                  <MarkdownRenderer :content="throttledStreamingContent" :streaming="sending" />
                  <span class="cursor" v-if="sending">▌</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Thinking State - only show when no streaming content yet AND no tools running -->
          <div v-if="sending && !streamingContent.trim() && !streamingThinkContent && streamingToolCallResults.length === 0" class="message-block assistant">
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
          <!-- Enabled Skills & Tools Display -->
          <div v-if="activeSkillName || toolsStore.enabledTools.length > 0" class="enabled-bar-container">
            <!-- Active Skill Display -->
            <div v-if="activeSkillName" class="enabled-skills-bar">
              <span class="skills-label">技能:</span>
              <el-tag
                size="small"
                type="warning"
                closable
                @close="deactivateSkill"
              >
                {{ skillsStore.getSkillByName(activeSkillName)?.display_name || activeSkillName }}
              </el-tag>
            </div>

            <!-- Enabled Tools Display -->
            <div v-if="toolsStore.enabledTools.length > 0" class="enabled-tools-bar">
              <span class="tools-label">工具:</span>
              <el-tag
                v-for="tool in visibleTools"
                :key="tool.id"
                size="small"
                class="tool-tag"
              >
                {{ tool.name }}
              </el-tag>
              <el-tag v-if="hiddenToolsCount > 0" size="small" type="info" class="more-tools-tag">
                +{{ hiddenToolsCount }}
              </el-tag>
            </div>
            <!-- Empty state -->
            <div v-else class="add-tools-bar">
              <span class="add-tools-label">工具: 无</span>
            </div>
          </div>

          <!-- Tool Selector Dialog -->
          <el-dialog
            v-model="showToolSelector"
            title="选择工具"
            width="400px"
            class="tool-selector-dialog"
          >
            <div class="tool-selector-content">
              <div class="tool-selector-header">
                <span>点击切换工具启用状态</span>
                <el-button size="small" link type="primary" class="manage-tools-btn" @click="router.push('/tools')">
                  <el-icon><Setting /></el-icon>
                  管理自定义工具
                </el-button>
              </div>
              <div class="tool-list">
                <div
                  v-for="tool in toolsStore.allTools"
                  :key="tool.id"
                  class="tool-item"
                  :class="{ enabled: toolsStore.isToolEnabled(tool.id) }"
                  @click="toolsStore.toggleTool(tool.id)"
                >
                  <div class="tool-info">
                    <span class="tool-name">{{ tool.name }}</span>
                    <span class="tool-desc">{{ tool.description.slice(0, 50) }}{{ tool.description.length > 50 ? '...' : '' }}</span>
                  </div>
                  <el-icon v-if="toolsStore.isToolEnabled(tool.id)" class="tool-check"><Check /></el-icon>
                </div>
              </div>
            </div>
            <template #footer>
              <el-button @click="showToolSelector = false">完成</el-button>
            </template>
          </el-dialog>

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

              <el-dropdown trigger="click" @command="setThinkingMode" v-if="currentConversation">
                <button class="action-btn" :class="{ active: thinkingMode !== 'auto' }">
                  <el-icon><Cpu /></el-icon>
                  <span>思维链</span>
                  <span class="mode-tag">{{ thinkingModeLabel }}</span>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="auto" :class="{ 'is-active': thinkingMode === 'auto' }">
                      <span class="option-label">自动</span>
                      <span class="option-desc">不设置参数</span>
                    </el-dropdown-item>
                    <el-dropdown-item command="high" :class="{ 'is-active': thinkingMode === 'high' }">
                      <span class="option-label">高</span>
                      <span class="option-desc">深度思考</span>
                    </el-dropdown-item>
                    <el-dropdown-item command="medium" :class="{ 'is-active': thinkingMode === 'medium' }">
                      <span class="option-label">中</span>
                      <span class="option-desc">适中思考</span>
                    </el-dropdown-item>
                    <el-dropdown-item command="low" :class="{ 'is-active': thinkingMode === 'low' }">
                      <span class="option-label">低</span>
                      <span class="option-desc">轻度思考</span>
                    </el-dropdown-item>
                    <el-dropdown-item command="minimal" :class="{ 'is-active': thinkingMode === 'minimal' }">
                      <span class="option-label">最小</span>
                      <span class="option-desc">Gemini MINIMAL</span>
                    </el-dropdown-item>
                    <el-dropdown-item command="none" :class="{ 'is-active': thinkingMode === 'none' }">
                      <span class="option-label">不开</span>
                      <span class="option-desc">禁用思考</span>
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
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from '@/plugins/element-plus-services'
import {
  Plus, Setting, ChatLineRound, Monitor,
  Loading, Promotion, MoreFilled, Delete, MagicStick, Close, Menu, Paperclip, Operation,
  Timer,
  Edit, RefreshRight, DocumentCopy, Collection, Check, Cpu, WarningFilled
} from '@element-plus/icons-vue'
import { conversationApi, modelApi } from '@/api/conversation'
import type { Conversation, Message, ConversationSettings, PresetPrompt, ChatContentPart, ChatRequest, ChatMessage, OpenAIReasoningEffort, GeminiThinkingLevel, ChatModelOption } from '@/types/conversation'
import { PRESET_PROMPTS } from '@/types/conversation'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import ThinkBlock from '@/components/chat/ThinkBlock.vue'
import ToolCallDisplay from '@/components/chat/ToolCallDisplay.vue'
import AttachmentPreview from '@/components/chat/AttachmentPreview.vue'
import { parseMessageContent, parseStreamingThinkContent, estimateThinkTokens, removeThinkContent, parseXmlToolCalls } from '@/utils/messageParser'
import { compressImage, isImageFile, formatFileSize } from '@/utils/imageUtils'
import { useToolsStore } from '@/stores/tools'
import { useImageStore } from '@/stores/image'
import { useSkillsStore } from '@/stores/skills'
import type { ToolCallResult, ToolCall } from '@/types/tool'
import { executeToolCall, setMessagesForToolExecution } from '@/utils/toolExecutor'

// Tools store
const toolsStore = useToolsStore()

// Image store (for yolo-draw)
const imageStore = useImageStore()

// Skills store (for agent skills)
const skillsStore = useSkillsStore()

// Router
const route = useRoute()
const router = useRouter()

// Clean tokenizer artifacts from model output (e.g., Gemma's <|...|> tokens)
function cleanTokenizerArtifacts(str: string): string {
  // Gemma-style special tokens: <|...|> patterns
  // These can appear in various forms:
  // - Complete: <|token|>
  // - Incomplete/split: <| ... |>, <|, |>
  // - In JSON context: "<|\" or "\"|" (escaped quotes with tokenizer boundaries)

  let cleaned = str

  // 1. Remove complete <|...|> patterns (including escaped versions)
  // Match <| followed by any characters until |>
  cleaned = cleaned.replace(/<\\?\|[^>|]*\\?\|>/g, '')

  // 2. Remove incomplete <| patterns (tokenizer start that wasn't closed)
  // <| or <\| followed by optional characters
  cleaned = cleaned.replace(/<\\?\|[^\s,\}\]]*/g, '')

  // 3. Remove standalone | or \| that appear after quote marks (tokenizer boundary)
  // Pattern: "\"|" or "\|" at end of a JSON string value
  cleaned = cleaned.replace(/\"\\?\|/g, '"')
  cleaned = cleaned.replace(/\\?\|\"/g, '"')

  // 4. Remove any remaining <| or |>
  cleaned = cleaned.replace(/<\\?\|/g, '')
  cleaned = cleaned.replace(/\\?\|>/g, '')

  // 5. Clean up double quotes that might have been affected
  // Remove empty string artifacts like "" that might result from cleanup
  // But preserve legitimate empty strings in JSON

  return cleaned
}

// Safely parse JSON with artifact cleanup
function safeParseJson(str: string): Record<string, unknown> {
  if (!str || str.trim() === '') {
    return {}
  }

  try {
    const cleaned = cleanTokenizerArtifacts(str)
    return JSON.parse(cleaned)
  } catch (e) {
    // If still fails, try more aggressive cleanup
    try {
      // Remove any remaining special characters that might break JSON
      let aggressiveClean = str
        // Remove all <| and |> variants
        .replace(/<\\?\|[^>|]*\\?\|>/g, '')
        .replace(/<\\?\|/g, '')
        .replace(/\\?\|>/g, '')
        // Remove | that appears in suspicious contexts (after/before quotes)
        .replace(/\"\\?\|/g, '"')
        .replace(/\\?\|\"/g, '"')
        // Remove any remaining | that's not part of valid JSON syntax
        .replace(/\\?\|(?![\s,\}\]])/g, '')
        // Remove unescaped control characters
        .replace(/[\x00-\x1F]/g, '')

      return JSON.parse(aggressiveClean)
    } catch {
      // Return empty object if all parsing attempts fail
      return {}
    }
  }
}

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

// Scroll state - track if user is at bottom and if user scrolled during output
const isUserAtBottom = ref(true)
const userHasScrolledDuringOutput = ref(false)

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

// Temporary conversation support - conversations that don't persist to database
const isTemporaryConversation = ref(false)
const TEMPORARY_CONVERSATION_ID = -1 // Special ID for temporary conversations
const models = ref<ChatModelOption[]>([])
const selectedModel = ref('')

// LocalStorage key for remembering user's preferred model
const LAST_USED_MODEL_KEY = 'ai-gateway-last-used-model'
const inputContent = ref('')
const sending = ref(false)
const streamingContent = ref('')
const showSettingsDialog = ref(false)
const presets = ref<PresetPrompt[]>(PRESET_PROMPTS)

// Active skill state - skill instructions appended to system prompt
const activeSkillName = ref<string | null>(null)
const activeSkillInstructions = ref<string | null>(null)

// Streaming state for Think and ToolCalls
const streamingThinkContent = ref('')
const streamingHasExplicitReasoning = ref(false)  // Track if reasoning field received (not from thinking tags)
const streamingToolCallResults = ref<ToolCallResult[]>([])
const showToolSelector = ref(false)

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
    // Handle explicit reasoning vs thinking tags format
    let finalContent: string
    let finalThinkContent: string
    let savedRawContent: string

    if (streamingHasExplicitReasoning.value) {
      finalContent = streamingContent.value
      finalThinkContent = streamingThinkContent.value
      savedRawContent = finalThinkContent.length > 0
        ? `<reasoning>${finalThinkContent}</reasoning>\n${finalContent}`
        : finalContent
    } else {
      const parsed = parseStreamingThinkContent(streamingRawContent.value)
      finalContent = parsed.text
      finalThinkContent = parsed.think
      savedRawContent = streamingRawContent.value
    }

    const assistantMsg: ExtendedMessage = {
      id: -Date.now(),
      conversation_id: currentConversation.value!.id,
      role: 'assistant',
      content: finalContent,
      thinkContent: finalThinkContent,
      hasThink: finalThinkContent.length > 0,
      toolCalls: streamingToolCallResults.value.length > 0 ? streamingToolCallResults.value : undefined,
      created_at: new Date().toISOString()
    }
    messages.value.push(assistantMsg)

    // Save to history
    await saveAssistantMessage(currentConversation.value!.id, savedRawContent, streamingToolCallResults.value.length > 0 ? streamingToolCallResults.value : undefined)
  }

  // Clear streaming state
  sending.value = false
  streamingRawContent.value = ''
  streamingContent.value = ''
  streamingThinkContent.value = ''
  streamingHasExplicitReasoning.value = false
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
  error?: string
  hasError?: boolean
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
    arguments: safeParseJson(tc.function.arguments || '{}'),
    status: 'running'
  }))

  // Update UI with running status
  if (onToolResult) onToolResult(results)

  // Execute each tool
  for (let i = 0; i < results.length; i++) {
    const toolCall = results[i]
    try {
      // 设置当前消息列表，供 yolo_draw 等工具使用
      setMessagesForToolExecution(messages.value.map(m => ({
        role: m.role,
        content: m.content
      })))
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
  temperature: 1,
  max_tokens: 4096,
  top_p: 0.95,
  system_prompt: ''
})

// Thinking/reasoning effort mode
type ThinkingMode = 'auto' | 'high' | 'medium' | 'low' | 'minimal' | 'none'
const thinkingMode = ref<ThinkingMode>('auto')

const selectedModelMeta = computed(() => {
  return models.value.find(model => model.name === selectedModel.value) || null
})

const currentModelLabel = computed(() => {
  return selectedModelMeta.value?.alias || selectedModelMeta.value?.name || '未选择模型'
})

const thinkingModeLabel = computed(() => {
  const labels: Record<ThinkingMode, string> = {
    auto: '自动',
    high: '高',
    medium: '中',
    low: '低',
    minimal: '最小',
    none: '不开'
  }
  return labels[thinkingMode.value]
})

const setThinkingMode = (mode: ThinkingMode) => {
  thinkingMode.value = mode
}

// Get thinking config for API request - supports OpenAI, Gemini, and DeepSeek/Ollama formats
const getThinkingConfig = (): {
  think?: boolean
  reasoning_effort?: OpenAIReasoningEffort
  generationConfig?: { thinkingConfig?: { thinkingLevel?: GeminiThinkingLevel } }
} | undefined => {
  if (thinkingMode.value === 'auto') return undefined

  // DeepSeek/Ollama format: think (boolean)
  const thinkMap: Record<ThinkingMode, boolean | undefined> = {
    auto: undefined,
    high: undefined,    // think doesn't have levels
    medium: undefined,
    low: undefined,
    minimal: undefined,
    none: false         // think: false to disable thinking
  }

  // OpenAI format: reasoning_effort
  const reasoningEffortMap: Record<ThinkingMode, OpenAIReasoningEffort | undefined> = {
    auto: undefined,
    high: 'high',
    medium: 'medium',
    low: 'low',
    minimal: undefined,  // minimal only for Gemini
    none: 'none'
  }

  // Gemini format: thinkingLevel
  const thinkingLevelMap: Record<ThinkingMode, GeminiThinkingLevel | undefined> = {
    auto: undefined,
    high: 'HIGH',
    medium: 'MEDIUM',
    low: 'LOW',
    minimal: 'MINIMAL',
    none: 'NONE'
  }

  const thinkValue = thinkMap[thinkingMode.value]
  const effort = reasoningEffortMap[thinkingMode.value]
  const level = thinkingLevelMap[thinkingMode.value]

  return {
    think: thinkValue,
    reasoning_effort: effort,
    generationConfig: level ? { thinkingConfig: { thinkingLevel: level } } : undefined
  }
}

// Build request with thinking config
const buildRequestWithThinking = (baseRequest: ChatRequest): ChatRequest => {
  const thinkingConfig = getThinkingConfig()
  if (!thinkingConfig) return baseRequest

  return {
    ...baseRequest,
    think: thinkingConfig.think,
    reasoning_effort: thinkingConfig.reasoning_effort,
    generationConfig: thinkingConfig.generationConfig
  }
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

  // Delete messages from database (skip for temporary conversations)
  const prevMessageId = userIndex > 0 ? messages.value[userIndex - 1]?.id : 0

  if (!isTemporaryConversation.value) {
    try {
      await conversationApi.deleteMessagesAfter(currentConversation.value.id, prevMessageId)
    } catch (e) {
      console.error('Failed to delete messages:', e)
    }
  }

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
  userHasScrolledDuringOutput.value = false

  // Save user message to database (skip for temporary conversations)
  if (!isTemporaryConversation.value) {
    try {
      await conversationApi.addMessage(currentConversation.value.id, {
        role: 'user',
        content: userContent
      })
    } catch (e) {
      console.error('Failed to save user message:', e)
    }
  }

  // Build full messages array
  // buildChatHistory() already includes the user message we just added
  const messagesForApi = buildChatHistory()

  // Send the message
  sending.value = true
  await streamWithToolCalls(buildRequestWithThinking({
    model: selectedModel.value,
    messages: messagesForApi,
    stream: true,
    temperature: settingsForm.temperature,
    max_tokens: settingsForm.max_tokens,
    tools: toolsStore.getToolsForModel()
  }))
}

// Retry last message after an error
const retryLastMessage = async () => {
  if (!currentConversation.value || sending.value) return

  // Find and remove the last error message
  const lastErrorIndex = messages.value.findIndex((m, idx) =>
    idx === messages.value.length - 1 && (m as ExtendedMessage).hasError
  )
  if (lastErrorIndex === -1) return

  messages.value = messages.value.slice(0, lastErrorIndex)

  // Find the last user message
  const lastUserIndex = messages.value.length - 1
  const lastUserMessage = messages.value[lastUserIndex]
  if (!lastUserMessage || lastUserMessage.role !== 'user') return

  // Build messages for API
  const messagesForApi = buildChatHistory()

  // Retry sending
  sending.value = true
  await streamWithToolCalls(buildRequestWithThinking({
    model: selectedModel.value,
    messages: messagesForApi,
    stream: true,
    temperature: settingsForm.temperature,
    max_tokens: settingsForm.max_tokens,
    tools: toolsStore.getToolsForModel()
  }))
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

  // Get the message ID before this message (for deletion)
  // deleteMessagesAfter deletes messages with id > prevMessageId
  // So if prevMessageId = 0, it deletes all messages (id > 0)
  const prevMessageId = originalIndex > 0 ? messages.value[originalIndex - 1]?.id : 0

  // 删除该消息之后的消息（本地）
  messages.value = messages.value.slice(0, originalIndex)

  // Delete messages from database (skip for temporary conversations)
  if (!isTemporaryConversation.value) {
    try {
      await conversationApi.deleteMessagesAfter(currentConversation.value.id, prevMessageId)
    } catch (e) {
      console.error('Failed to delete messages:', e)
    }
  }

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
  userHasScrolledDuringOutput.value = false

  // Save user message to database (skip for temporary conversations)
  if (!isTemporaryConversation.value) {
    try {
      await conversationApi.addMessage(currentConversation.value.id, {
        role: 'user',
        content: newContentToStore
      })
    } catch (e) {
      console.error('Failed to save user message:', e)
    }
  }

  // Build full messages array
  // buildChatHistory() already includes the user message we just added
  const messagesForApi = buildChatHistory()

  // 发送消息
  sending.value = true
  await streamWithToolCalls(buildRequestWithThinking({
    model: selectedModel.value,
    messages: messagesForApi,
    stream: true,
    temperature: settingsForm.temperature,
    max_tokens: settingsForm.max_tokens,
    tools: toolsStore.getToolsForModel()
  }))
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

// Generate title in background (non-blocking)
const generateTitleInBackground = async (conversationId: number) => {
  try {
    const response = await conversationApi.generateTitle(conversationId)
    const newTitle = response.data.data?.title
    if (newTitle && currentConversation.value?.id === conversationId) {
      // Update current conversation title
      currentConversation.value.title = newTitle
      // Update in conversations list
      const convInList = conversations.value.find(c => c.id === conversationId)
      if (convInList) {
        convInList.title = newTitle
      }
    }
  } catch (e) {
    // Silently fail - title generation is optional
    console.error('Failed to generate title:', e)
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
      // Try to use last used model from localStorage
      const lastUsedModel = localStorage.getItem(LAST_USED_MODEL_KEY)
      if (lastUsedModel && models.value.some(m => m.name === lastUsedModel)) {
        selectedModel.value = lastUsedModel
      } else {
        selectedModel.value = models.value[0].name
      }
    }
  } catch (error) {
    console.error('Failed to load models:', error)
  }
}

// Create new conversation
const createNewConversation = async (temporary = false) => {
  if (temporary) {
    // Create temporary conversation (not saved to database)
    const model = selectedModel.value || models.value[0]?.name || 'gpt-3.5-turbo'
    const tempConv: Conversation = {
      id: TEMPORARY_CONVERSATION_ID,
      user_id: 0,
      title: '临时对话',
      model,
      system_prompt: '',
      settings: { temperature: 0.7, max_tokens: 4096, top_p: 0.9 },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    }
    isTemporaryConversation.value = true
    currentConversation.value = tempConv
    messages.value = []
    selectedModel.value = model
    inputContent.value = ''
    if (isMobile.value) sidebarOpen.value = false
    nextTick(() => textareaRef.value?.focus())
    return
  }

  // Create regular conversation (saved to database)
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
  // Reset temporary conversation flag when selecting a real conversation
  isTemporaryConversation.value = conv.id === TEMPORARY_CONVERSATION_ID

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
                  arguments: typeof tc.function?.arguments === 'string' ? safeParseJson(tc.function.arguments) : tc.function?.arguments || {},
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

// Activate a skill by name (appended to system prompt)
const activateSkill = (skillName: string) => {
  // If empty skillName, deactivate current skill
  if (!skillName) {
    activeSkillName.value = null
    activeSkillInstructions.value = null
    ElMessage.success('已取消技能')
    return
  }

  const skill = skillsStore.getSkillByName(skillName)
  if (skill) {
    activeSkillName.value = skill.name
    activeSkillInstructions.value = skill.instructions || null
    ElMessage.success(`已激活技能: ${skill.display_name || skill.name}`)
  } else {
    ElMessage.warning('未找到该技能')
  }
}

// Deactivate current skill
const deactivateSkill = () => {
  activeSkillName.value = null
  activeSkillInstructions.value = null
}

// Update model - also save to localStorage for future conversations
const updateModel = async () => {
  // Save to localStorage for remembering user's preference
  if (selectedModel.value) {
    localStorage.setItem(LAST_USED_MODEL_KEY, selectedModel.value)
  }

  if (currentConversation.value && selectedModel.value !== currentConversation.value.model) {
    // Skip API update for temporary conversations
    if (isTemporaryConversation.value) {
      currentConversation.value.model = selectedModel.value
      return
    }

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
  streamingHasExplicitReasoning.value = false
  throttledStreamingContent.value = ''
  throttledStreamingThink.value = ''
  streamingToolCallResults.value = []
  if (throttleTimer) {
    clearTimeout(throttleTimer)
    throttleTimer = null
  }
  const content = inputContent.value.trim()
  inputContent.value = ''

  // Reset textarea height after clearing content
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }

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
  userHasScrolledDuringOutput.value = false
  scrollToBottom()

  // Save user message to database first (skip for temporary conversations)
  if (!isTemporaryConversation.value) {
    try {
      await conversationApi.addMessage(currentConversation.value.id, {
        role: 'user',
        content: contentToStore
      })
    } catch (e) {
      console.error('Failed to save user message:', e)
    }
  }

  // Build full messages array for API request
  // buildChatHistory() already includes the user message we just added to messages.value
  const messagesForApi = buildChatHistory()

  // Start the streaming loop with tool call support
  sending.value = true
  await streamWithToolCalls(buildRequestWithThinking({
    model: selectedModel.value,
    messages: messagesForApi,
    stream: true,
    temperature: settingsForm.temperature,
    max_tokens: settingsForm.max_tokens,
    tools: toolsStore.getToolsForModel()
  }))
}

// Helper function to save assistant message to backend
const saveAssistantMessage = async (conversationId: number, content: string, toolCalls?: ToolCallResult[]) => {
  // Skip saving for temporary conversations
  if (isTemporaryConversation.value || conversationId === TEMPORARY_CONVERSATION_ID) {
    return
  }

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
    let systemContent = settingsForm.system_prompt

    // Add skills catalog if available
    const skillsXML = skillsStore.getSkillsForModel()
    if (skillsXML) {
      systemContent += '\n\n' + skillsXML
    }

    history.push({
      role: 'system',
      content: systemContent
    })
  } else {
    // If no system prompt but skills exist, add skills as system message
    const skillsXML = skillsStore.getSkillsForModel()
    if (skillsXML) {
      history.push({
        role: 'system',
        content: `You have access to the following skills:\n\n${skillsXML}\n\nWhen a task matches a skill's description, consider using its instructions to guide your response.`
      })
    }
  }

  // Add active skill instructions after system prompt
  if (activeSkillInstructions.value) {
    history.push({
      role: 'system',
      content: `[Active Skill: ${activeSkillName.value}]\n\n${activeSkillInstructions.value}`
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
  streamingHasExplicitReasoning.value = false
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
      conversationApi.streamChat(
        requestData,
        (text) => {
          // Only update rawContent if no explicit reasoning (to avoid mixing)
          if (!streamingHasExplicitReasoning.value) {
            streamingRawContent.value += text
            const parsed = parseStreamingThinkContent(streamingRawContent.value)
            streamingContent.value = parsed.text
            if (parsed.think) {
              streamingThinkContent.value = parsed.think
            }
          } else {
            // With explicit reasoning, rawContent only stores content part (accumulate)
            streamingContent.value += text
            streamingRawContent.value += text
          }
          updateThrottledContent()
          throttledScrollToBottom()
        },
        () => {
          // Stream completed - check for XML format tool calls
          const { toolCalls: xmlToolCalls, cleanedContent } = parseXmlToolCalls(streamingRawContent.value)

          if (xmlToolCalls.length > 0) {
            streamingRawContent.value = cleanedContent
            const parsed = parseStreamingThinkContent(cleanedContent)
            streamingContent.value = parsed.text
            streamingThinkContent.value = parsed.think
            throttledStreamingContent.value = parsed.text
            throttledStreamingThink.value = parsed.think

            receivedToolCalls = xmlToolCalls
            streamingToolCallResults.value = xmlToolCalls.map(tc => ({
              id: tc.id,
              toolName: tc.function.name,
              arguments: safeParseJson(tc.function.arguments || '{}'),
              status: 'running'
            }))
          } else {
            throttledStreamingContent.value = streamingContent.value
            throttledStreamingThink.value = streamingThinkContent.value
          }

          if (throttleTimer) {
            clearTimeout(throttleTimer)
            throttleTimer = null
          }

          resolve()
        },
        (error) => {
          const errorMsg: ExtendedMessage = {
            id: -Date.now(),
            conversation_id: currentConversation.value?.id || 0,
            role: 'assistant',
            content: '',
            error: error,
            hasError: true,
            created_at: new Date().toISOString()
          }
          messages.value.push(errorMsg)
          sending.value = false
          streamingRawContent.value = ''
          streamingContent.value = ''
          streamingThinkContent.value = ''
          streamingHasExplicitReasoning.value = false
          throttledStreamingContent.value = ''
          throttledStreamingThink.value = ''
          streamingToolCallResults.value = []
          if (throttleTimer) {
            clearTimeout(throttleTimer)
            throttleTimer = null
          }
          reject(new Error(error))
        },
        (reasoning) => {
          // Handle explicit reasoning field (from models like Gemma)
          streamingHasExplicitReasoning.value = true
          streamingThinkContent.value += reasoning
          updateThrottledContent()
          throttledScrollToBottom()
        },
        async (toolCalls) => {
          receivedToolCalls = toolCalls
          streamingToolCallResults.value = toolCalls.map(tc => ({
            id: tc.id,
            toolName: tc.function.name,
            arguments: safeParseJson(tc.function.arguments || '{}'),
            status: 'running'
          }))

          const results = await executeToolCallsAndContinue(
            toolCalls,
            currentConversation.value?.id || 0,
            (updatedResults) => {
              streamingToolCallResults.value = updatedResults
            }
          )

          if (userStoppedStream) {
            resolve()
            return
          }

          const savedRawContent = streamingRawContent.value
          const savedContent = streamingContent.value
          const savedThinkContent = streamingThinkContent.value
          const savedHasThink = streamingThinkContent.value.length > 0

          streamingRawContent.value = ''
          streamingContent.value = ''
          streamingThinkContent.value = ''
          streamingHasExplicitReasoning.value = false
          throttledStreamingContent.value = ''
          throttledStreamingThink.value = ''
          streamingToolCallResults.value = []
          if (throttleTimer) {
            clearTimeout(throttleTimer)
            throttleTimer = null
          }

          const toolResultsContent = results.map(r =>
            `Tool: ${r.toolName}\nResult: ${JSON.stringify(r.result ?? r.error)}`
          ).join('\n\n')

          const assistantMsg: ExtendedMessage = {
            id: -Date.now(),
            conversation_id: currentConversation.value?.id || 0,
            role: 'assistant',
            content: savedContent,
            thinkContent: savedThinkContent,
            hasThink: savedHasThink,
            toolCalls: results,
            created_at: new Date().toISOString()
          }
          messages.value.push(assistantMsg)

          scrollToBottom()

          const messagesForApi = buildChatHistory()

          // Save assistant message (if not temporary)
          if (!isTemporaryConversation.value && currentConversation.value) {
            await saveAssistantMessage(currentConversation.value.id, savedRawContent, results)
            try {
              await conversationApi.addMessage(currentConversation.value.id, {
                role: 'tool',
                content: toolResultsContent
              })
            } catch (e) {
              console.error('Failed to save tool results message:', e)
            }
          }

          await streamWithToolCalls(
            buildRequestWithThinking({
              model: selectedModel.value,
              messages: messagesForApi,
              stream: true,
              temperature: settingsForm.temperature,
              max_tokens: settingsForm.max_tokens,
              tools: toolsStore.getToolsForModel()
            }),
            iteration + 1
          ).catch(console.error)
          resolve()
        },
        abortController?.signal
      )
    })

    // Finalize the message if no tool calls and user didn't stop
    if (receivedToolCalls.length === 0 && !userStoppedStream) {
      // Handle explicit reasoning (from models like Gemma) vs thinking tags format
      let finalContent: string
      let finalThinkContent: string
      let savedRawContent: string

      if (streamingHasExplicitReasoning.value) {
        // Explicit reasoning field - use streaming values directly
        finalContent = streamingContent.value
        finalThinkContent = streamingThinkContent.value
        // Wrap think content with thinking tags for storage
        savedRawContent = finalThinkContent.length > 0
          ? `<think>${finalThinkContent}</think>\n${finalContent}`
          : finalContent
      } else {
        // Thinking tags format - parse from raw content
        const rawContent = streamingRawContent.value
        const parsed = parseStreamingThinkContent(rawContent)
        finalContent = parsed.text
        finalThinkContent = parsed.think
        savedRawContent = rawContent
      }

      const assistantMsg: ExtendedMessage = {
        id: -Date.now(),
        conversation_id: currentConversation.value?.id || 0,
        role: 'assistant',
        content: finalContent,
        thinkContent: finalThinkContent,
        hasThink: finalThinkContent.length > 0,
        toolCalls: streamingToolCallResults.value,
        created_at: new Date().toISOString()
      }
      messages.value.push(assistantMsg)

      // Save final message to history (if not temporary)
      if (!isTemporaryConversation.value && currentConversation.value) {
        await saveAssistantMessage(currentConversation.value.id, savedRawContent, streamingToolCallResults.value)
      }

      // Clear streaming state AFTER adding message
      await new Promise(resolve => setTimeout(resolve, 50))
      streamingRawContent.value = ''
      streamingContent.value = ''
      streamingThinkContent.value = ''
      streamingHasExplicitReasoning.value = false
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

      // Auto-generate title if this is the first user message
      const userMessageCount = messages.value.filter(m => m.role === 'user').length
      if (userMessageCount === 1 && currentConversation.value?.title === 'New Chat' && !isTemporaryConversation.value && currentConversation.value) {
        generateTitleInBackground(currentConversation.value.id)
      }
    }

    // Handle XML format tool calls detected after stream completion
    if (receivedToolCalls.length > 0 && receivedToolCalls[0].id.startsWith('xml_tool_') && !userStoppedStream) {
      // XML format tool calls - execute them now
      const xmlToolCalls = receivedToolCalls

      // Execute tools
      const results = await executeToolCallsAndContinue(
        xmlToolCalls,
        currentConversation.value?.id || 0,
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
        conversation_id: currentConversation.value?.id || 0,
        role: 'assistant',
        content: savedContent,
        thinkContent: savedThinkContent,
        hasThink: savedHasThink,
        toolCalls: results,
        created_at: new Date().toISOString()
      }
      messages.value.push(assistantMsg)

      scrollToBottom()

      // NOW build messages for next request using buildChatHistory
      const messagesForApi = buildChatHistory()

      // Save assistant message to history (if not temporary)
      if (!isTemporaryConversation.value && currentConversation.value) {
        await saveAssistantMessage(currentConversation.value.id, savedRawContent, results)
        try {
          await conversationApi.addMessage(currentConversation.value.id, {
            role: 'tool',
            content: toolResultsContent
          })
        } catch (e) {
          console.error('Failed to save tool results message:', e)
        }
      }

      // Clear streaming state
      streamingRawContent.value = ''
      streamingContent.value = ''
      streamingThinkContent.value = ''
      streamingHasExplicitReasoning.value = false
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
        buildRequestWithThinking({
          model: selectedModel.value,
          messages: messagesForApi,
          stream: true,
          temperature: settingsForm.temperature,
          max_tokens: settingsForm.max_tokens,
          tools: toolsStore.getToolsForModel()
        }),
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


// Scroll to bottom (only if user hasn't scrolled during this output)
const scrollToBottom = () => {
  if (messagesAreaRef.value && !userHasScrolledDuringOutput.value) {
    messagesAreaRef.value.scrollTop = messagesAreaRef.value.scrollHeight
  }
}

// Handle scroll event
let scrollTimeout: ReturnType<typeof setTimeout> | null = null
const handleScroll = () => {
  if (messagesAreaRef.value) {
    const { scrollTop, scrollHeight, clientHeight } = messagesAreaRef.value
    const atBottom = scrollHeight - scrollTop - clientHeight < 150
    isUserAtBottom.value = atBottom

    // Immediately detect if user scrolled up during output - stop auto-scroll
    if (!atBottom && sending.value) {
      userHasScrolledDuringOutput.value = true
    }
  }

  // Debounce for other scroll-related checks
  if (scrollTimeout) {
    clearTimeout(scrollTimeout)
  }
  scrollTimeout = setTimeout(() => {
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

  // 如果是图片，保存到 imageStore（用于 yolo-draw）
  if (isImage) {
    const imageId = `image_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    imageStore.addImage({
      id: imageId,
      dataUrl,
      createdAt: Date.now()
    })
  }
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

// 获取某个消息块之前的所有消息（用于 YoloRedrawDisplay 查找图片）
const getRequestMessagesForBlock = (block: ExpandedMessageBlock) => {
  // 返回从第一条消息到该块所在消息的所有消息
  // 格式化为 ToolCallDisplay 所需的格式
  return messages.value.slice(0, block.originalIndex + 1).map(m => ({
    role: m.role,
    content: m.content
  }))
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

  // Skip API update for temporary conversations, just update local state
  if (isTemporaryConversation.value) {
    currentConversation.value.model = selectedModel.value
    currentConversation.value.system_prompt = settingsForm.system_prompt
    showSettingsDialog.value = false
    return
  }

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
  } else if (action === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('请输入新标题', '重命名', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValue: conv.title,
        inputPattern: /^.{1,100}$/,
        inputErrorMessage: '标题长度需要在1-100字符之间'
      })
      if (value) {
        await conversationApi.updateTitle(conv.id, value)
        conv.title = value
        if (currentConversation.value?.id === conv.id) {
          currentConversation.value.title = value
        }
        ElMessage.success('标题已更新')
      }
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

  // Handle skill activation from query parameter
  if (route.query.activateSkill) {
    const skillName = route.query.activateSkill as string
    // Wait for skills to be loaded
    setTimeout(() => {
      activateSkill(skillName)
    }, 500)
  }
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
  background:
    radial-gradient(circle at top left, rgba(14, 165, 233, 0.18), transparent 30%),
    radial-gradient(circle at top right, rgba(249, 115, 22, 0.14), transparent 26%),
    linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
  position: relative;
}

@media (max-width: 767px) {
  .chat-page {
    height: calc(100vh - 90px);
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
  background: rgba(255, 255, 255, 0.84);
  backdrop-filter: blur(18px);
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(148, 163, 184, 0.2);
  transition: transform 0.3s ease;
  flex-shrink: 0;
  box-shadow: 18px 0 40px rgba(15, 23, 42, 0.06);
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
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
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

.new-chat-buttons {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.new-chat-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 55%, #0ea5e9 100%);
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
  box-shadow: 0 12px 24px rgba(29, 78, 216, 0.22);
}

.temp-chat-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 12px;
  background: linear-gradient(135deg, #f97316 0%, #fb923c 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.temp-chat-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 24px rgba(249, 115, 22, 0.22);
}

.temporary-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #c2410c;
}

.temporary-indicator .el-icon {
  font-size: 14px;
}

.temp-hint {
  font-size: 12px;
  color: #9a3412;
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
  background: rgba(255, 255, 255, 0.72);
}

.conversation-item.active {
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.12), rgba(37, 99, 235, 0.14));
  box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.12);
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
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #9ca3af;
  margin-top: 2px;
}

.conv-model {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-mode-tag {
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.08);
  color: #2563eb;
  font-size: 11px;
  font-weight: 600;
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
  background: transparent;
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.72);
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
  backdrop-filter: blur(14px);
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

.title-panel {
  display: flex;
  align-items: center;
  gap: 16px;
}

.title-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.conversation-name {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.selector-cluster {
  display: flex;
  align-items: center;
  gap: 10px;
}

.model-selector :deep(.el-select) {
  width: 180px;
}

@media (max-width: 767px) {
  .model-selector :deep(.el-select) {
    width: 140px;
  }

  .title-panel {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .selector-cluster {
    width: 100%;
    flex-wrap: wrap;
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

.mode-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.86);
  color: #334155;
  font-size: 12px;
  font-weight: 700;
}

.mode-badge.chat {
  color: #0369a1;
}

.mode-badge.responses {
  color: #1d4ed8;
  background: linear-gradient(135deg, rgba(219, 234, 254, 0.92), rgba(239, 246, 255, 0.96));
}

.mode-badge.compact {
  padding: 6px 10px;
}

.mode-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: currentColor;
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.12);
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
  background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 55%, #0ea5e9 100%);
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
  box-shadow: 0 12px 24px rgba(29, 78, 216, 0.22);
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
  padding: 20px 16px;
  min-height: 0;
}

.welcome-screen {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.welcome-content {
  width: min(760px, 100%);
  padding: 20px;
}

.welcome-hero {
  display: grid;
  grid-template-columns: 92px 1fr;
  gap: 20px;
  align-items: center;
  margin-bottom: 24px;
}

.hero-copy {
  text-align: left;
}

.hero-kicker {
  display: inline-block;
  margin-bottom: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
}

.welcome-icon {
  width: 92px;
  height: 92px;
  margin: 0;
  background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 55%, #0ea5e9 100%);
  border-radius: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 20px 40px rgba(29, 78, 216, 0.24);
}

.welcome-content h2 {
  font-size: 34px;
  font-weight: 700;
  line-height: 1.08;
  color: #0f172a;
  margin: 0 0 10px;
}

.welcome-content p {
  font-size: 15px;
  color: #475569;
  margin: 0 0 24px;
}

.quick-start {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.08);
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
  width: 260px;
}

.welcome-model-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.welcome-model-card,
.feature-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(241, 245, 249, 0.92));
  border: 1px solid rgba(148, 163, 184, 0.14);
  color: #0f172a;
}

.meta-label,
.feature-title {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.feature-desc {
  font-size: 13px;
  line-height: 1.5;
  color: #475569;
}

@media (max-width: 767px) {
  .welcome-hero {
    grid-template-columns: 1fr;
  }

  .hero-copy {
    text-align: center;
  }

  .welcome-icon {
    margin: 0 auto;
  }

  .welcome-content h2 {
    font-size: 28px;
  }

  .model-select-row {
    flex-direction: column;
  }

  .model-select-row :deep(.el-select) {
    width: 100%;
  }

  .welcome-model-meta,
  .feature-grid {
    grid-template-columns: 1fr;
  }

  .input-mode-bar {
    align-items: flex-start;
    flex-direction: column;
  }
}

.start-buttons {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.start-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 28px;
  background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 55%, #0ea5e9 100%);
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
  box-shadow: 0 18px 32px rgba(29, 78, 216, 0.24);
}

.start-btn.temp {
  background: linear-gradient(135deg, #f97316 0%, #fb923c 100%);
}

.start-btn.temp:hover {
  box-shadow: 0 18px 32px rgba(249, 115, 22, 0.24);
}

.messages-container {
  max-width: 860px;
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
  line-height: 1.5;
  word-break: break-word;
}

/* User message markdown - compact style */
.user-bubble :deep(.markdown-content) {
  line-height: 1.5;
}

.user-bubble :deep(.markdown-content p) {
  margin: 0 0 6px 0;
}

.user-bubble :deep(.markdown-content p:last-child) {
  margin-bottom: 0;
}

/* Remove extra margin when p is followed by code block */
.user-bubble :deep(.markdown-content p + .code-block) {
  margin-top: 4px;
}

.user-bubble :deep(.markdown-content .code-block) {
  margin: 6px 0;
}

.user-bubble :deep(.markdown-content .code-block:first-child) {
  margin-top: 0;
}

.user-bubble :deep(.markdown-content .code-block:last-child) {
  margin-bottom: 0;
}

.user-bubble :deep(.markdown-content .code-header) {
  padding: 4px 10px;
}

.user-bubble :deep(.markdown-content pre) {
  padding: 8px 10px;
}

.user-bubble :deep(.markdown-content code) {
  font-size: 13px;
}

.user-bubble :deep(.markdown-content :not(pre) > code) {
  padding: 1px 4px;
  font-size: 13px;
}

.user-bubble :deep(.markdown-content ul),
.user-bubble :deep(.markdown-content ol) {
  margin: 4px 0;
  padding-left: 16px;
}

.user-bubble :deep(.markdown-content li) {
  margin: 2px 0;
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

/* Error bubble styles */
.error-bubble {
  display: flex;
  align-items: center;
  gap: 12px;
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border: 1px solid #fecaca;
  padding: 12px 16px;
  border-radius: 8px;
  max-width: 85%;
}

.error-icon {
  color: #ef4444;
  font-size: 20px;
}

.error-text {
  color: #991b1b;
  font-size: 14px;
  flex: 1;
}

.retry-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #ef4444;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
}

.retry-btn:hover {
  background: #dc2626;
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
  background: rgba(255, 255, 255, 0.72);
  border-top: 1px solid rgba(148, 163, 184, 0.16);
  backdrop-filter: blur(14px);
}

.input-container {
  max-width: 860px;
  margin: 0 auto;
}

.input-mode-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 16px;
  background: rgba(241, 245, 249, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.input-mode-text {
  font-size: 12px;
  color: #475569;
}

/* Enabled Bar Container */
.enabled-bar-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

/* Enabled Skills Bar */
.enabled-skills-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
  overflow: hidden;
}

.skills-label {
  font-size: 12px;
  color: #e6a23c;
  font-weight: 500;
  flex-shrink: 0;
}

.enabled-skills-bar :deep(.el-tag) {
  font-size: 11px;
  flex-shrink: 0;
}

/* Enabled Tools Bar */
.enabled-tools-bar {
  display: flex;
  align-items: center;
  gap: 6px;
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
  cursor: pointer;
}

/* Tool tags bar */
.enabled-tools-bar {
  border-radius: 8px;
}

/* Add tools bar */
.add-tools-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 8px;
}

.add-tools-label {
  font-size: 12px;
  color: #9ca3af;
}

/* Tool Selector Dialog */
.tool-selector-content {
  max-height: 400px;
  overflow-y: auto;
}

.tool-selector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.manage-tools-btn {
  padding: 4px 8px;
}

.tool-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
  border: 1px solid #e5e7eb;
}

.tool-item:hover {
  background: #f9fafb;
}

.tool-item.enabled {
  background: #f0fdf4;
  border-color: #22c55e;
}

.tool-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.tool-name {
  font-weight: 500;
  color: #374151;
}

.tool-desc {
  font-size: 12px;
  color: #6b7280;
}

.tool-check {
  color: #22c55e;
  font-size: 18px;
}

/* Input Box */
.input-box {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  background: rgba(248, 250, 252, 0.95);
  border-radius: 24px;
  padding: 12px 14px;
  transition: all 0.2s;
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
}

.input-box:focus-within {
  border-color: #2563eb;
  background: #fff;
  box-shadow: 0 16px 32px rgba(37, 99, 235, 0.12);
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

/* Skill dropdown option */
.skill-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 0;
}

.skill-name {
  font-weight: 500;
  color: #374151;
}

.skill-name.text-warning {
  color: #e6a23c;
}

.skill-desc {
  font-size: 12px;
  color: #6b7280;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Header tools row */
.header-tools-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
