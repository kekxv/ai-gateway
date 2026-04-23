import { ref, nextTick, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-plus-services'
import { conversationApi } from '@/api/conversation'
import type { Conversation, Message } from '@/types/conversation'
import type { ToolCallResult } from '@/types/tool'
import { parseMessageContent } from '@/utils/messageParser'

// Special ID for temporary conversations
export const TEMPORARY_CONVERSATION_ID = -1

// Extended message type with think and tool_calls
export interface ExtendedMessage extends Message {
  thinkContent?: string
  hasThink?: boolean
  toolCalls?: ToolCallResult[]
  error?: string
  hasError?: boolean
}

export function useChatConversation(
  models: Ref<{ name: string; alias?: string }[]>,
  selectedModel: Ref<string>,
  isMobile: Ref<boolean>,
  sidebarOpen: Ref<boolean>,
  focusTextarea?: () => void,
  initSettings?: (conv: Conversation) => void,
  loadMessagesHandler?: (convId: number) => Promise<ExtendedMessage[]>,
  scrollToBottom?: () => void
) {
  // State
  const conversations = ref<Conversation[]>([])
  const currentConversation = ref<Conversation | null>(null)
  const messages = ref<ExtendedMessage[]>([])
  const isTemporaryConversation = ref(false)
  const isLoadingMessages = ref(false)

  // Load conversations list
  const loadConversations = async () => {
    try {
      const response = await conversationApi.list()
      conversations.value = response.data.data || []
    } catch (error) {
      console.error('Failed to load conversations:', error)
    }
  }

  // Generate title in background (non-blocking)
  const generateTitleInBackground = async (conversationId: number) => {
    try {
      const response = await conversationApi.generateTitle(conversationId)
      const newTitle = response.data.data?.title
      if (newTitle && currentConversation.value?.id === conversationId) {
        currentConversation.value.title = newTitle
        const convInList = conversations.value.find(c => c.id === conversationId)
        if (convInList) {
          convInList.title = newTitle
        }
      }
    } catch (e) {
      console.error('Failed to generate title:', e)
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
      if (isMobile.value) sidebarOpen.value = false
      if (focusTextarea) focusTextarea()
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
      await selectConversation(newConv)
      if (isMobile.value) sidebarOpen.value = false
      if (focusTextarea) focusTextarea()
    } catch {
      ElMessage.error('创建对话失败')
    }
  }

  // Select conversation
  const selectConversation = async (conv: Conversation) => {
    // Reset temporary conversation flag
    isTemporaryConversation.value = conv.id === TEMPORARY_CONVERSATION_ID

    currentConversation.value = conv
    selectedModel.value = conv.model

    // Initialize settings
    if (initSettings) {
      initSettings(conv)
    }

    // Show loading state
    isLoadingMessages.value = true
    messages.value = []

    // Load messages using handler or default
    try {
      if (loadMessagesHandler) {
        messages.value = await loadMessagesHandler(conv.id)
      } else {
        try {
          const response = await conversationApi.getMessages(conv.id)
          const rawMessages = response.data.data || []
          messages.value = processRawMessages(rawMessages)
        } catch (error) {
          console.error('Failed to load messages:', error)
          messages.value = []
        }
      }
    } finally {
      isLoadingMessages.value = false
    }

    // Scroll to bottom
    await nextTick()
    if (scrollToBottom) scrollToBottom()
    if (isMobile.value) sidebarOpen.value = false
  }

  // Process raw messages from API
  const processRawMessages = (rawMessages: Message[]): ExtendedMessage[] => {
    const processedMessages: ExtendedMessage[] = []
    const toolResultsMap = new Map<string, string>()

    // First pass: collect tool results
    rawMessages.forEach((msg: Message) => {
      if (msg.role === 'tool' || (msg.role === 'user' && msg.content.startsWith('Tool: '))) {
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

    // Second pass: build message list
    rawMessages.forEach((msg: Message) => {
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
                  arguments: typeof tc.function?.arguments === 'string'
                    ? JSON.parse(tc.function.arguments)
                    : tc.function?.arguments || {},
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

    return processedMessages
  }

  // Handle conversation action (delete, rename)
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

  // Update conversation (for settings)
  const updateConversation = async (id: number, data: Partial<Conversation>) => {
    try {
      await conversationApi.update(id, data)
    } catch {
      ElMessage.error('更新对话失败')
    }
  }

  return {
    conversations,
    currentConversation,
    messages,
    isTemporaryConversation,
    isLoadingMessages,
    TEMPORARY_CONVERSATION_ID,
    loadConversations,
    generateTitleInBackground,
    createNewConversation,
    selectConversation,
    handleConversationAction,
    updateConversation,
    processRawMessages
  }
}