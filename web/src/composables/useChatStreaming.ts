import { ref, computed, type Ref } from 'vue'
import { conversationApi } from '@/api/conversation'
import {
  parseStreamingThinkContent,
  parseXmlToolCalls
} from '@/utils/messageParser'
import type { ChatRequest, ChatMessage } from '@/types/conversation'
import type { ToolCall, ToolCallResult } from '@/types/tool'
import type { ExtendedMessage } from './useChatConversation'

// Max iterations for tool calls
const MAX_TOOL_ITERATIONS = 5

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

export function useChatStreaming(
  currentConversation: Ref<{ id: number; title?: string } | null>,
  messages: Ref<ExtendedMessage[]>,
  isTemporaryConversation: Ref<boolean>,
  selectedModel: Ref<string>,
  settingsForm: Ref<{
    temperature: number
    max_tokens: number
    top_p: number
  }>,
  buildChatHistory: () => ChatMessage[],
  buildRequestWithThinking: (request: ChatRequest) => ChatRequest,
  getToolsForModel: () => Array<{
    type: string
    function: {
      name: string
      description: string
      parameters: Record<string, unknown>
    }
  }> | undefined,
  executeToolCalls: (toolCalls: ToolCall[], convId: number, onResult?: (results: ToolCallResult[]) => void) => Promise<ToolCallResult[]>,
  saveAssistantMessage: (convId: number, content: string, toolCalls?: ToolCallResult[]) => Promise<void>,
  scrollToBottom: () => void,
  loadConversations: () => Promise<void>,
  generateTitleInBackground: (convId: number) => Promise<void>
) {
  // Streaming state
  const sending = ref(false)
  const streamingRawContent = ref('')
  const streamingContent = ref('')
  const streamingThinkContent = ref('')
  const streamingHasExplicitReasoning = ref(false)
  const streamingToolCallResults = ref<ToolCallResult[]>([])

  // Throttled streaming content for rendering
  const throttledStreamingContent = ref('')
  const throttledStreamingThink = ref('')
  let throttleTimer: ReturnType<typeof setTimeout> | null = null

  // AbortController for stopping stream
  let abortController: AbortController | null = null
  let userStoppedStream = false

  // Computed: is any tool running
  const isAnyToolRunning = computed(() =>
    streamingToolCallResults.value.some(tc => tc.status === 'running')
  )

  // Update throttled content at most every 200ms
  const updateThrottledContent = () => {
    if (throttleTimer) return
    throttleTimer = setTimeout(() => {
      throttledStreamingContent.value = streamingContent.value
      throttledStreamingThink.value = streamingThinkContent.value
      throttleTimer = null
    }, 200)
  }

  // Throttled scroll to bottom (max once per 100ms)
  const throttledScrollToBottom = throttle(() => {
    requestAnimationFrame(() => scrollToBottom())
  }, 100)

  // Stop streaming and save partial content
  const stopStreaming = async () => {
    if (!abortController) return

    userStoppedStream = true
    abortController.abort()
    abortController = null

    // Save partial content if any
    if (streamingContent.value || streamingThinkContent.value) {
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
      await saveAssistantMessage(
        currentConversation.value!.id,
        savedRawContent,
        streamingToolCallResults.value.length > 0 ? streamingToolCallResults.value : undefined
      )
    }

    // Clear streaming state
    clearStreamingState()
  }

  // Clear streaming state
  const clearStreamingState = () => {
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

  // Reset streaming state for new request
  const resetStreamingState = () => {
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
    userStoppedStream = false
    abortController = new AbortController()
  }

  // Streaming loop that handles tool calls recursively
  const streamWithToolCalls = async (
    requestData: ChatRequest,
    iteration: number = 0
  ): Promise<void> => {
    // Check iteration limit
    if (iteration >= MAX_TOOL_ITERATIONS) {
      console.warn('Max tool iterations reached, stopping')
      sending.value = false
      return
    }

    // Reset streaming state
    resetStreamingState()

    // Track if tool calls were received
    let receivedToolCalls: ToolCall[] = []

    try {
      await new Promise<void>((resolve, reject) => {
        conversationApi.streamChat(
          requestData,
          (text) => {
            // Handle content
            if (!streamingHasExplicitReasoning.value) {
              streamingRawContent.value += text
              const parsed = parseStreamingThinkContent(streamingRawContent.value)
              streamingContent.value = parsed.text
              if (parsed.think) {
                streamingThinkContent.value = parsed.think
              }
            } else {
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
                arguments: JSON.parse(tc.function.arguments || '{}'),
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
            clearStreamingState()
            reject(new Error(error))
          },
          (reasoning) => {
            // Handle explicit reasoning field
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
              arguments: JSON.parse(tc.function.arguments || '{}'),
              status: 'running'
            }))

            const results = await executeToolCalls(
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

            // Save current content
            const savedRawContent = streamingRawContent.value
            const savedContent = streamingContent.value
            const savedThinkContent = streamingThinkContent.value
            const savedHasThink = streamingThinkContent.value.length > 0

            // Clear streaming state
            resetStreamingState()

            // Build tool results content
            const toolResultsContent = results.map(r =>
              `Tool: ${r.toolName}\nResult: ${JSON.stringify(r.result ?? r.error)}`
            ).join('\n\n')

            // Add assistant message
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

            // Build messages for next request
            const messagesForApi = buildChatHistory()

            // Save to history
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

            // Continue streaming
            await streamWithToolCalls(
              buildRequestWithThinking({
                model: selectedModel.value,
                messages: messagesForApi,
                stream: true,
                temperature: settingsForm.value.temperature,
                max_tokens: settingsForm.value.max_tokens,
                tools: getToolsForModel()
              }),
              iteration + 1
            ).catch(console.error)
            resolve()
          },
          abortController?.signal
        )
      })

      // Finalize message if no tool calls and user didn't stop
      if (receivedToolCalls.length === 0 && !userStoppedStream) {
        finalizeMessage()
      }

      // Handle XML format tool calls after stream completion
      if (receivedToolCalls.length > 0 && receivedToolCalls[0].id.startsWith('xml_tool_') && !userStoppedStream) {
        await handleXmlToolCalls(receivedToolCalls, iteration)
      }
    } catch (error) {
      console.error('Streaming error:', error)
    } finally {
      if (receivedToolCalls.length === 0) {
        sending.value = false
      }
    }
  }

  // Finalize message after streaming
  const finalizeMessage = async () => {
    let finalContent: string
    let finalThinkContent: string
    let savedRawContent: string

    if (streamingHasExplicitReasoning.value) {
      finalContent = streamingContent.value
      finalThinkContent = streamingThinkContent.value
      savedRawContent = finalThinkContent.length > 0
        ? `<think>${finalThinkContent}</think>\n${finalContent}`
        : finalContent
    } else {
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

    // Save to history
    if (!isTemporaryConversation.value && currentConversation.value) {
      await saveAssistantMessage(currentConversation.value.id, savedRawContent, streamingToolCallResults.value)
    }

    // Delay before clearing
    await new Promise(resolve => setTimeout(resolve, 50))
    clearStreamingState()

    // Update conversation list
    if (messages.value.length <= 3) {
      await loadConversations()
    }

    // Auto-generate title
    const userMessageCount = messages.value.filter(m => m.role === 'user').length
    if (userMessageCount === 1 && currentConversation.value?.title === 'New Chat' && !isTemporaryConversation.value && currentConversation.value) {
      await generateTitleInBackground(currentConversation.value.id)
    }
  }

  // Handle XML format tool calls
  const handleXmlToolCalls = async (xmlToolCalls: ToolCall[], iteration: number) => {
    const results = await executeToolCalls(
      xmlToolCalls,
      currentConversation.value?.id || 0,
      (updatedResults) => {
        streamingToolCallResults.value = updatedResults
      }
    )

    // Save current content
    const savedRawContent = streamingRawContent.value
    const savedContent = streamingContent.value
    const savedThinkContent = streamingThinkContent.value
    const savedHasThink = streamingThinkContent.value.length > 0

    // Build tool results content
    const toolResultsContent = results.map(r =>
      `Tool: ${r.toolName}\nResult: ${JSON.stringify(r.result ?? r.error)}`
    ).join('\n\n')

    // Add assistant message
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

    // Build messages for next request
    const messagesForApi = buildChatHistory()

    // Save to history
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

    // Clear and continue
    clearStreamingState()
    scrollToBottom()

    await streamWithToolCalls(
      buildRequestWithThinking({
        model: selectedModel.value,
        messages: messagesForApi,
        stream: true,
        temperature: settingsForm.value.temperature,
        max_tokens: settingsForm.value.max_tokens,
        tools: getToolsForModel()
      }),
      iteration + 1
    ).catch(console.error)
  }

  return {
    sending,
    streamingRawContent,
    streamingContent,
    streamingThinkContent,
    streamingHasExplicitReasoning,
    streamingToolCallResults,
    throttledStreamingContent,
    throttledStreamingThink,
    isAnyToolRunning,
    stopStreaming,
    streamWithToolCalls,
    clearStreamingState
  }
}