import { api } from './index'
import type { Conversation, Message, CreateConversationRequest, UpdateConversationRequest, ChatRequest } from '@/types/conversation'
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

  // Send a message (non-streaming)
  sendMessage: (id: number, data: ChatRequest) =>
    api.post<{ data: Message; usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number } }>(`/conversations/${id}/chat`, { ...data, stream: false }),

  // Send a message with streaming
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
                // Handle tool calls
                if (delta.tool_calls && Array.isArray(delta.tool_calls)) {
                  for (const tc of delta.tool_calls) {
                    toolCalls.push({
                      id: tc.id || `tool_${Date.now()}`,
                      type: 'function',
                      function: {
                        name: tc.function?.name || '',
                        arguments: tc.function?.arguments || '{}'
                      }
                    })
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