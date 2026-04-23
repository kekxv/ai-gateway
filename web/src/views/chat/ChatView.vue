<template>
  <div class="chat-page">
    <!-- Sidebar -->
    <ChatSidebar
      :sidebar-open="sidebarOpen"
      :is-mobile="isMobile"
      :conversations="conversations"
      :current-conversation="currentConversation"
      :is-temporary-conversation="isTemporaryConversation"
      @update:sidebar-open="sidebarOpen = $event"
      @new-conversation="createNewConversation"
      @select-conversation="selectConversation"
      @conversation-action="handleConversationAction"
    />

    <!-- Main Content -->
    <main class="main-content">
      <!-- Header -->
      <ChatHeader
        :current-conversation="currentConversation"
        :is-mobile="isMobile"
        :sidebar-open="sidebarOpen"
        :models="models"
        :selected-model="selectedModel"
        :active-skill-name="activeSkillName"
        :enabled-skills="skillsStore.enabledSkills"
        :all-tools="toolsStore.allTools"
        :enabled-tools="toolsStore.enabledTools"
        @update:sidebar-open="sidebarOpen = $event"
        @update:selected-model="updateModel"
        @update:show-settings="showSettingsDialog = true"
        @new-conversation="createNewConversation"
        @activate-skill="activateSkill"
        @toggle-tool="toolsStore.toggleTool"
      />

      <!-- Messages Area -->
      <ChatMessageList
        ref="messageListRef"
        :expanded-messages="expandedMessages"
        :messages="messages"
        :sending="sending"
        :streaming-content="throttledStreamingContent"
        :streaming-think="throttledStreamingThink"
        :streaming-tool-calls="streamingToolCallResults"
        :is-any-tool-running="isAnyToolRunning"
        :editing-block-id="editingBlockId"
        :editing-content="editingContent"
        :is-user-at-bottom="isUserAtBottom"
        :user-has-scrolled-during-output="userHasScrolledDuringOutput"
        @update:editing-block-id="editingBlockId = $event"
        @update:editing-content="editingContent = $event"
        @update:is-user-at-bottom="isUserAtBottom = $event"
        @update:user-has-scrolled-during-output="userHasScrolledDuringOutput = $event"
        @start-edit="startEditBlock"
        @cancel-edit="cancelEdit"
        @confirm-edit="confirmEditBlock"
        @regenerate="regenerateFromUser"
        @delete="deleteMessage"
        @copy="copyMessage"
        @retry="retryLastMessage"
        @edit-keydown="handleEditKeydown"
      />

      <!-- Input Area -->
      <ChatInputArea
        ref="inputAreaRef"
        :current-conversation="currentConversation"
        :is-mobile="isMobile"
        :sending="sending"
        :input-content="inputContent"
        :attached-files="attachedFiles"
        :active-skill-name="activeSkillName"
        :active-skill-display-name="activeSkillDisplayName"
        :enabled-tools="toolsStore.enabledTools"
        :presets="presets"
        :thinking-mode="thinkingMode"
        :thinking-mode-label="thinkingModeLabel"
        @update:input-content="inputContent = $event"
        @send="sendMessage"
        @stop-streaming="stopStreaming"
        @trigger-upload="triggerUpload"
        @file-upload="handleFileUpload"
        @paste="handlePaste"
        @remove-file="removeFile"
        @deactivate-skill="deactivateSkill"
        @apply-preset="applyPresetWrapper"
        @set-thinking-mode="setThinkingMode"
      />
    </main>

    <!-- Settings Dialog -->
    <ChatSettingsDialog
      v-model="showSettingsDialog"
      :settings="settingsForm"
      @save="saveSettings"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from '@/plugins/element-plus-services'
import { conversationApi, modelApi } from '@/api/conversation'

// Stores
import { useToolsStore } from '@/stores/tools'
import { useSkillsStore } from '@/stores/skills'

// Composables
import { useChatSettings, type ThinkingMode } from '@/composables/useChatSettings'
import { useChatFiles } from '@/composables/useChatFiles'
import { useChatConversation } from '@/composables/useChatConversation'
import { useChatTools } from '@/composables/useChatTools'
import { useChatStreaming } from '@/composables/useChatStreaming'
import { useChatMessages } from '@/composables/useChatMessages'

// Components
import ChatSidebar from './components/ChatSidebar.vue'
import ChatHeader from './components/ChatHeader.vue'
import ChatMessageList from './components/ChatMessageList.vue'
import ChatInputArea from './components/ChatInputArea.vue'
import ChatSettingsDialog from './components/ChatSettingsDialog.vue'

// Types
import type { Conversation, ChatModelOption } from '@/types/conversation'

// Stores
const toolsStore = useToolsStore()
const skillsStore = useSkillsStore()
const route = useRoute()

// Refs for UI
const isMobile = ref(false)
const sidebarOpen = ref(false)
const models = ref<ChatModelOption[]>([])
const selectedModel = ref('')
const inputContent = ref('')
const showSettingsDialog = ref(false)

// LocalStorage key
const LAST_USED_MODEL_KEY = 'ai-gateway-last-used-model'

// Scroll state
const isUserAtBottom = ref(true)
const userHasScrolledDuringOutput = ref(false)

// Component refs
const messageListRef = ref<{ scrollToBottom: () => void } | null>(null)
const inputAreaRef = ref<{ focusTextarea: () => void; textareaRef: HTMLTextAreaElement | null; fileInputRef: HTMLInputElement | null } | null>(null)

// Helper refs
const textareaRef = computed(() => inputAreaRef.value?.textareaRef)
const fileInputRef = computed(() => inputAreaRef.value?.fileInputRef)

// Scroll helper
const scrollToBottom = () => {
  messageListRef.value?.scrollToBottom()
}

// Focus textarea helper
const focusTextarea = () => {
  inputAreaRef.value?.focusTextarea()
}

// Use composables
const settingsComposable = useChatSettings(
  ref(null) as any, // Will be updated after conversation is set
  ref(false),
  selectedModel
)

const filesComposable = useChatFiles(
  fileInputRef as any,
  ref(null) as any,
  ref(false)
)

const conversationComposable = useChatConversation(
  models,
  selectedModel,
  isMobile,
  sidebarOpen,
  focusTextarea,
  (conv) => settingsComposable.initSettingsFromConversation(conv),
  async (convId) => {
    // Load messages handler - returns processed messages
    const response = await conversationApi.getMessages(convId)
    return conversationComposable.processRawMessages(response.data.data || [])
  },
  scrollToBottom
)

const toolsComposable = useChatTools(
  conversationComposable.messages
)

const streamingComposable = useChatStreaming(
  conversationComposable.currentConversation,
  conversationComposable.messages,
  conversationComposable.isTemporaryConversation,
  selectedModel,
  settingsComposable.settingsForm as any,
  () => messagesComposable.buildChatHistory(),
  (request) => settingsComposable.buildRequestWithThinking(request),
  () => toolsStore.getToolsForModel(),
  toolsComposable.executeToolCallsAndContinue,
  async (convId, content, toolCalls) => {
    // Save assistant message
    if (conversationComposable.isTemporaryConversation.value) return
    try {
      let toolCallsStr = ''
      if (toolCalls && toolCalls.length > 0) {
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
      await conversationApi.addMessage(convId, {
        role: 'assistant',
        content,
        tool_calls: toolCallsStr || undefined
      })
    } catch (e) {
      console.error('Failed to save assistant message:', e)
    }
  },
  scrollToBottom,
  conversationComposable.loadConversations,
  conversationComposable.generateTitleInBackground
)

const messagesComposable = useChatMessages(
  conversationComposable.currentConversation,
  conversationComposable.messages,
  conversationComposable.isTemporaryConversation,
  selectedModel,
  settingsComposable.settingsForm as any,
  toolsComposable.activeSkillName,
  toolsComposable.activeSkillInstructions,
  filesComposable.attachedFiles,
  inputContent,
  textareaRef as any,
  streamingComposable.sending,
  isUserAtBottom,
  userHasScrolledDuringOutput,
  scrollToBottom,
  streamingComposable.streamWithToolCalls,
  (request) => settingsComposable.buildRequestWithThinking(request),
  filesComposable.clearFiles
)

// Expose values from composables
const { thinkingMode, thinkingModeLabel, presets, setThinkingMode, applyPreset } = settingsComposable
const settingsForm = settingsComposable.settingsForm
const { attachedFiles, triggerUpload, handleFileUpload: handleFileUploadEvent, handlePaste: handlePasteEvent, removeFile } = filesComposable
const { conversations, currentConversation, messages, isTemporaryConversation, loadConversations, createNewConversation, selectConversation, handleConversationAction } = conversationComposable
const { activeSkillName, activateSkill, deactivateSkill } = toolsComposable
const { sending, streamingToolCallResults, throttledStreamingContent, throttledStreamingThink, isAnyToolRunning, stopStreaming } = streamingComposable
const { expandedMessages, editingBlockId, editingContent, startEditBlock, cancelEdit, handleEditKeydown, confirmEditBlock, deleteMessage, copyMessage, regenerateFromUser, retryLastMessage, sendMessage } = messagesComposable

// Computed
const activeSkillDisplayName = computed(() => {
  if (!activeSkillName.value) return ''
  const skill = skillsStore.getSkillByName(activeSkillName.value)
  return skill?.display_name || skill?.name || activeSkillName.value
})

// Methods
const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
  if (!isMobile.value) {
    sidebarOpen.value = true
  }
}

const loadModels = async () => {
  try {
    const response = await modelApi.listForChat()
    models.value = response.data || []
    if (models.value.length > 0 && !selectedModel.value) {
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

const updateModel = async (modelName: string) => {
  selectedModel.value = modelName
  if (modelName) {
    localStorage.setItem(LAST_USED_MODEL_KEY, modelName)
  }

  if (currentConversation.value && modelName !== currentConversation.value.model) {
    if (isTemporaryConversation.value) {
      currentConversation.value.model = modelName
      return
    }

    try {
      await conversationComposable.updateConversation(currentConversation.value.id, { model: modelName })
      currentConversation.value.model = modelName
    } catch {
      ElMessage.error('更新模型失败')
    }
  }
}

const saveSettings = async (settings: any) => {
  if (settingsForm.value) {
    Object.assign(settingsForm.value, settings)
  }
  const success = await settingsComposable.saveSettings()
  if (success) {
    showSettingsDialog.value = false
    ElMessage.success('设置已保存')
  } else {
    ElMessage.error('保存失败')
  }
}

const applyPresetWrapper = (presetId: string) => {
  applyPreset(presetId, inputContent, focusTextarea)
}

const handleFileUpload = async (event: Event) => {
  await handleFileUploadEvent(event)
}

const handlePaste = async (event: ClipboardEvent) => {
  await handlePasteEvent(event)
}

// Lifecycle
onMounted(() => {
  checkMobile()
  loadConversations()
  loadModels()
  window.addEventListener('resize', checkMobile)

  // Handle skill activation from query parameter
  if (route.query.activateSkill) {
    const skillName = route.query.activateSkill as string
    setTimeout(() => {
      activateSkill(skillName)
    }, 500)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
  // Stop any ongoing stream when leaving
  if (streamingComposable.sending.value) {
    stopStreaming()
  }
})
</script>

<style scoped>
@import "./ChatView.css";
</style>