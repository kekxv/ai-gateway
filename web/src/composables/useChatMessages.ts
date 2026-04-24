import { ref, computed, nextTick, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from '@/plugins/element-plus-services'
import { conversationApi } from '@/api/conversation'
import {
  removeThinkContent
} from '@/utils/messageParser'
import type { ChatMessage, ChatContentPart } from '@/types/conversation'
import type { ExtendedMessage } from './useChatConversation'
import { useToolsStore } from '@/stores/tools'
import { useSkillsStore } from '@/stores/skills'

// Expanded message block for display
export interface ExpandedMessageBlock {
  id: number | string
  originalId: number
  originalIndex: number
  role: string
  type: 'text' | 'image'
  content: string
  part?: ChatContentPart
  message: ExtendedMessage
}

export function useChatMessages(
  currentConversation: Ref<{ id: number; title: string } | null>,
  messages: Ref<ExtendedMessage[]>,
  isTemporaryConversation: Ref<boolean>,
  selectedModel: Ref<string>,
  settingsForm: Ref<{
    temperature: number
    max_tokens: number
    top_p: number
    system_prompt: string
  }>,
  activeSkillName: Ref<string | null>,
  activeSkillInstructions: Ref<string | null>,
  attachedFiles: Ref<Array<{ dataUrl: string; filename: string; isImage: boolean; part: { type: string; image_url?: { url: string } } }>>,
  inputContent: Ref<string>,
  textareaRef: Ref<HTMLTextAreaElement | null>,
  sending: Ref<boolean>,
  isUserAtBottom: Ref<boolean>,
  userHasScrolledDuringOutput: Ref<boolean>,
  scrollToBottom: () => void,
  streamWithToolCalls: (requestData: any, iteration?: number) => Promise<void>,
  buildRequestWithThinking: (request: any) => any,
  clearAttachedFiles: () => void
) {
  const toolsStore = useToolsStore()
  const skillsStore = useSkillsStore()

  // Edit state
  const editingBlockId = ref<string | number | null>(null)
  const editingContent = ref('')
  const editTextareaRef = ref<HTMLTextAreaElement | null>(null)

  // Parse message content from DB (multimodal format)
  const parseMessageContentFromDB = (content: string): ChatContentPart[] => {
    try {
      const parts = JSON.parse(content)
      if (Array.isArray(parts) && parts.length > 0 && parts[0].type) {
        return parts as ChatContentPart[]
      }
    } catch {
      // Not JSON, treat as plain text
    }
    return []
  }

  // Expanded messages for display
  const expandedMessages = computed<ExpandedMessageBlock[]>(() => {
    const result: ExpandedMessageBlock[] = []

    messages.value.forEach((msg, index) => {
      const parts = parseMessageContentFromDB(msg.content)

      if (parts.length > 0 && msg.role === 'user') {
        // Multimodal message: expand to multiple blocks
        // Show image blocks first
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
        // Then show text block
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
        // Plain text message or assistant message
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

  // Build chat history for API request
  const buildChatHistory = (): ChatMessage[] => {
    const history: ChatMessage[] = []
    let combinedSystemContent = ''

    // 1. Add base system prompt
    if (settingsForm.value.system_prompt) {
      combinedSystemContent = settingsForm.value.system_prompt
    }

    // 2. Add skills catalog if auto-selection is enabled
    if (activeSkillName.value === 'auto') {
      const skillsXML = skillsStore.getSkillsForModel()
      if (skillsXML) {
        if (combinedSystemContent) combinedSystemContent += '\n\n'
        combinedSystemContent += `You have access to the following skills:\n\n${skillsXML}\n\nWhen a task matches a skill's description, consider using its instructions to guide your response.`
      }
    }

    // 3. Add active skill instructions if a specific skill is selected
    if (activeSkillInstructions.value) {
      if (combinedSystemContent) combinedSystemContent += '\n\n'
      combinedSystemContent += `[Active Skill: ${activeSkillName.value}]\n\n${activeSkillInstructions.value}`
    }

    // Push the combined system message if there is any content
    if (combinedSystemContent) {
      history.push({
        role: 'system',
        content: combinedSystemContent
      })
    }

    messages.value.forEach(msg => {
      // Format tool calls
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

      // Build message content
      let messageContent: string | ChatContentPart[]

      if (msg.role === 'assistant') {
        messageContent = removeThinkContent(msg.content)
      } else if (msg.role === 'user') {
        const parts = parseMessageContentFromDB(msg.content)
        if (parts.length > 0) {
          messageContent = parts
        } else {
          messageContent = msg.content
        }
      } else {
        messageContent = msg.content
      }

      history.push({
        role: msg.role,
        content: messageContent,
        tool_calls: formattedToolCalls
      })

      // Append tool results
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

  // Send message
  const sendMessage = async () => {
    if ((!inputContent.value.trim() && attachedFiles.value.length === 0) || !currentConversation.value || sending.value) return

    sending.value = true
    const content = inputContent.value.trim()
    inputContent.value = ''

    // Reset textarea height
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }

    // Build parts array
    const parts: ChatContentPart[] = []
    if (content) {
      parts.push({ type: 'text', text: content })
    }
    for (const file of attachedFiles.value) {
      if (file.part.image_url) {
        parts.push({ type: 'image_url', image_url: file.part.image_url })
      }
    }
    clearAttachedFiles()

    // Build content to store
    let contentToStore: string
    if (parts.length > 1 || (parts.length === 1 && parts[0].type === 'image_url')) {
      contentToStore = JSON.stringify(parts)
    } else {
      contentToStore = content
    }

    // Add user message
    const tempUserMsg: ExtendedMessage = {
      id: 0,
      conversation_id: currentConversation.value.id,
      role: 'user',
      content: contentToStore,
      created_at: new Date().toISOString()
    }
    messages.value.push(tempUserMsg)
    isUserAtBottom.value = true
    userHasScrolledDuringOutput.value = false
    scrollToBottom()

    // Save to database
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

    // Build messages for API
    const messagesForApi = buildChatHistory()

    // Start streaming
    await streamWithToolCalls(buildRequestWithThinking({
      model: selectedModel.value,
      messages: messagesForApi,
      stream: true,
      temperature: settingsForm.value.temperature,
      max_tokens: settingsForm.value.max_tokens,
      tools: toolsStore.getToolsForModel()
    }))
  }

  // Delete message
  const deleteMessage = async (messageIndex: number) => {
    if (!currentConversation.value) return

    try {
      await ElMessageBox.confirm('确定删除此消息及其后续消息？', '确认删除', { type: 'warning' })
      messages.value = messages.value.slice(0, messageIndex)
      ElMessage.success('已删除')
    } catch {
      // Cancelled
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

  // Regenerate from user message
  const regenerateFromUser = async (userIndex: number) => {
    if (!currentConversation.value || sending.value) return

    const userMessage = messages.value[userIndex]
    if (userMessage.role !== 'user') return

    const userContent = userMessage.content

    // Remove messages from this index
    messages.value = messages.value.slice(0, userIndex)

    // Delete from database
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

    // Save user message
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

    // Build messages and send
    const messagesForApi = buildChatHistory()
    sending.value = true
    await streamWithToolCalls(buildRequestWithThinking({
      model: selectedModel.value,
      messages: messagesForApi,
      stream: true,
      temperature: settingsForm.value.temperature,
      max_tokens: settingsForm.value.max_tokens,
      tools: toolsStore.getToolsForModel()
    }))
  }

  // Retry last message after error
  const retryLastMessage = async () => {
    if (!currentConversation.value || sending.value) return

    // Find and remove last error message
    const lastErrorIndex = messages.value.findIndex((m, idx) =>
      idx === messages.value.length - 1 && m.hasError
    )
    if (lastErrorIndex === -1) return

    messages.value = messages.value.slice(0, lastErrorIndex)

    // Find last user message
    const lastUserIndex = messages.value.length - 1
    const lastUserMessage = messages.value[lastUserIndex]
    if (!lastUserMessage || lastUserMessage.role !== 'user') return

    const messagesForApi = buildChatHistory()
    sending.value = true
    await streamWithToolCalls(buildRequestWithThinking({
      model: selectedModel.value,
      messages: messagesForApi,
      stream: true,
      temperature: settingsForm.value.temperature,
      max_tokens: settingsForm.value.max_tokens,
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

    const block = expandedMessages.value.find(b => b.id === editingBlockId.value)
    if (!block) return

    const newTextContent = editingContent.value.trim()
    const originalIndex = block.originalIndex
    const originalMessage = messages.value[originalIndex]

    cancelEdit()

    // Check if original message has images
    const originalParts = parseMessageContentFromDB(originalMessage.content)
    const imageParts = originalParts.filter(p => p.type === 'image_url')

    // Build new content
    let newContentToStore: string
    let newParts: ChatContentPart[] = []

    if (imageParts.length > 0) {
      newParts = [...imageParts]
      if (newTextContent) {
        newParts.push({ type: 'text', text: newTextContent })
      }
      newContentToStore = JSON.stringify(newParts)
    } else {
      newContentToStore = newTextContent
    }

    // Delete messages after this one
    const prevMessageId = originalIndex > 0 ? messages.value[originalIndex - 1]?.id : 0
    messages.value = messages.value.slice(0, originalIndex)

    if (!isTemporaryConversation.value) {
      try {
        await conversationApi.deleteMessagesAfter(currentConversation.value.id, prevMessageId)
      } catch (e) {
        console.error('Failed to delete messages:', e)
      }
    }

    // Add updated user message
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

    // Save user message
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

    // Build messages and send
    const messagesForApi = buildChatHistory()
    sending.value = true
    await streamWithToolCalls(buildRequestWithThinking({
      model: selectedModel.value,
      messages: messagesForApi,
      stream: true,
      temperature: settingsForm.value.temperature,
      max_tokens: settingsForm.value.max_tokens,
      tools: toolsStore.getToolsForModel()
    }))
  }

  // Get request messages for block (for ToolCallDisplay)
  const getRequestMessagesForBlock = (block: ExpandedMessageBlock) => {
    return messages.value.slice(0, block.originalIndex + 1).map(m => ({
      role: m.role,
      content: m.content
    }))
  }

  return {
    expandedMessages,
    editingBlockId,
    editingContent,
    editTextareaRef,
    buildChatHistory,
    sendMessage,
    deleteMessage,
    copyMessage,
    regenerateFromUser,
    retryLastMessage,
    startEditBlock,
    cancelEdit,
    handleEditKeydown,
    confirmEditBlock,
    parseMessageContentFromDB,
    getRequestMessagesForBlock
  }
}