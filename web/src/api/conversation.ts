import { api } from './index'
import type { Conversation, Message, CreateConversationRequest, UpdateConversationRequest, ChatRequest, ChatContentPart } from '@/types/conversation'
import type { ToolCall } from '@/types/tool'

export const conversationApi = {
  // List all conversations for current user
  list: () =>
    api.get<{ data: Conversation[] }>('/conversations'),

  // Create a new conversation
  create: (data: CreateConversationRequest) =>
    api.post<{ data: Conversation }>('/conversations', data),

  // Get a conversation by ID
  get: (id: number) =>
    api.get<{ data: Conversation }>(`/conversations/${id}`),

  // Update a conversation
  update: (id: number, data: UpdateConversationRequest) =>
    api.put<{ data: Conversation }>(`/conversations/${id}`, data),

  // Delete a conversation
  delete: (id: number) =>
    api.delete(`/conversations/${id}`),

  // Get messages for a conversation
  getMessages: (id: number) =>
    api.get<{ data: Message[] }>(`/conversations/${id}/messages`),

  // Add a message to a conversation
  addMessage: (id: number, data: { role: string; content: string; tool_calls?: string; tokens?: number }) =>
    api.post<{ data: Message }>(`/conversations/${id}/messages`, data),

  // Delete all messages after a specific message ID
  deleteMessagesAfter: (id: number, messageId: number) =>
    api.delete(`/conversations/${id}/messages/after/${messageId}`),

  // Generate title for conversation based on first user message
  generateTitle: (id: number) =>
    api.post<{ data: { title: string } }>(`/conversations/${id}/generate-title`),

  // Send a message with streaming (OpenAI-compatible format)
  // Frontend builds full request with model and messages
  sendMessageStream: async (
    id: number,
    data: ChatRequest,
    onContent: (content: string) => void,
    onDone: () => void,
    onError: (error: string) => void,
    onToolCall?: (toolCalls: ToolCall[]) => Promise<void>,
    abortSignal?: AbortSignal
  ) => {
    const token = localStorage.getItem('token')
    const baseURL = api.defaults.baseURL || '/api'

    try {
      const response = await fetch(`${baseURL}/conversations/${id}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ ...data, stream: true }),
        signal: abortSignal
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: '请求失败' }))
        onError(errorData.error || 'Request failed')
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        onError('No response body')
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''
      let inReasoning = false
      let toolCalls: ToolCall[] = []
      let toolCallsByIndex: Map<number, ToolCall> = new Map()  // Track tool calls by index for accumulation

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          // Close reasoning block if still open
          if (inReasoning) {
            onContent('</think>')
          }
          // If there are tool calls and we have a handler, execute them and continue
          if (toolCalls.length > 0 && onToolCall) {
            await onToolCall(toolCalls)
            // Tool execution is handled, stream will continue with tool results
            return
          }
          onDone()
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonData = line.slice(6)
            if (jsonData === '[DONE]') {
              // Close reasoning block if still open
              if (inReasoning) {
                onContent('</think>')
              }
              // If there are tool calls and we have a handler, execute them and continue
              if (toolCalls.length > 0 && onToolCall) {
                await onToolCall(toolCalls)
                return
              }
              onDone()
              break
            }
            try {
              const chunk = JSON.parse(jsonData)
              if (chunk.choices && chunk.choices[0]?.delta) {
                const delta = chunk.choices[0].delta
                // Handle reasoning content
                // Some models use 'reasoning', some 'reasoning_content'
                const reasoning = delta.reasoning || delta.reasoning_content

                if (reasoning) {
                  // Open think tag on first reasoning chunk
                  if (!inReasoning) {
                    inReasoning = true
                    onContent('<think>')
                  }
                  onContent(reasoning)
                }

                // Handle regular content
                // Check if content field exists (can be empty string)
                if (delta.content !== undefined && delta.content !== null) {
                  // If we were in reasoning mode, close the think tag first
                  // This happens when the model starts sending content
                  // We only close if the content is NOT empty, OR if reasoning is now empty/absent
                  if (inReasoning && (delta.content !== "" || !reasoning)) {
                    onContent('</think>')
                    inReasoning = false
                  }

                  if (delta.content) {
                    onContent(delta.content)
                  }
                }
                // Handle tool calls - accumulate arguments by index
                if (delta.tool_calls && Array.isArray(delta.tool_calls)) {
                  for (const tc of delta.tool_calls) {
                    const idx = tc.index ?? 0
                    const tcId = tc.id || ''
                    const tcName = tc.function?.name || ''
                    const tcArgs = tc.function?.arguments || ''

                    // Check if we already have a tool call at this index
                    const existing = toolCallsByIndex.get(idx)
                    if (existing) {
                      // Accumulate arguments (they come in fragments)
                      existing.function.arguments += tcArgs
                    } else if (tcId || tcName) {
                      // Create new tool call (first chunk has id and name)
                      const newToolCall: ToolCall = {
                        id: tcId || `tool_${Date.now()}_${idx}`,
                        type: 'function',
                        function: {
                          name: tcName,
                          arguments: tcArgs
                        }
                      }
                      toolCallsByIndex.set(idx, newToolCall)
                      toolCalls.push(newToolCall)
                    }
                  }
                }
              }
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
    } catch (err) {
      // Don't report error if request was aborted - silently return
      // The frontend's stopStreaming will handle saving partial content
      if (err instanceof Error && err.name === 'AbortError') {
        return
      }
      onError(err instanceof Error ? err.message : 'Stream error')
    }
  }
}

export const modelApi = {
  // Get available models for chat
  listForChat: () =>
    api.get<{ id: number; name: string; alias?: string }[]>('/models')
}

// Helper function to build user content from text and attached files
export function buildUserContent(text: string, parts?: ChatContentPart[]): ChatContentPart[] | string {
  if (!parts || parts.length === 0) {
    return text
  }
  // Add text content if provided
  const contentParts: ChatContentPart[] = []
  if (text) {
    contentParts.push({ type: 'text', text: text })
  }
  // Add attached files
  for (const part of parts) {
    if (part.type === 'image_url' && part.image_url) {
      contentParts.push({ type: 'image_url', image_url: part.image_url })
    }
  }
  // Return string if only text, otherwise return parts array
  if (contentParts.length === 1 && contentParts[0].type === 'text') {
    return contentParts[0].text || ''
  }
  return contentParts
}